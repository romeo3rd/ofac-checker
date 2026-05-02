from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, Response, status


SESSION_COOKIE = "ofac_session"
HASH_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 600_000
DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
MAX_FAILED_LOGIN_ATTEMPTS = 8

_login_lock = threading.Lock()
_failed_login_attempts: dict[str, list[float]] = {}


@dataclass(frozen=True)
class AuthConfig:
    users: dict[str, str]
    session_secret: str
    cookie_secure: bool
    session_ttl_seconds: int


def hash_password(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{HASH_SCHEME}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
        if scheme != HASH_SCHEME:
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
    except (TypeError, ValueError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def load_auth_config() -> AuthConfig:
    users = _parse_users(os.getenv("OFAC_AUTH_USERS", ""))
    session_secret = os.getenv("OFAC_SESSION_SECRET", "")
    if not users or len(session_secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )

    ttl_text = os.getenv("OFAC_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS))
    try:
        ttl_seconds = max(300, int(ttl_text))
    except ValueError:
        ttl_seconds = DEFAULT_SESSION_TTL_SECONDS

    return AuthConfig(
        users=users,
        session_secret=session_secret,
        cookie_secure=_env_bool("OFAC_COOKIE_SECURE", default=False),
        session_ttl_seconds=ttl_seconds,
    )


def is_auth_configured() -> bool:
    try:
        load_auth_config()
    except HTTPException:
        return False
    return True


def authenticate_user(username: str, password: str, config: AuthConfig) -> bool:
    stored_hash = config.users.get(username.strip())
    if not stored_hash:
        return False
    return verify_password(password, stored_hash)


def login_rate_key(username: str, request: Request) -> str:
    host = request.client.host if request.client else "unknown"
    return f"{host}:{username.strip().lower()}"


def check_login_rate_limit(key: str) -> None:
    now = time.time()
    with _login_lock:
        attempts = _recent_attempts(key, now)
        if len(attempts) >= MAX_FAILED_LOGIN_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed sign-in attempts. Try again later.",
            )
        _failed_login_attempts[key] = attempts


def record_failed_login(key: str) -> None:
    now = time.time()
    with _login_lock:
        attempts = _recent_attempts(key, now)
        attempts.append(now)
        _failed_login_attempts[key] = attempts


def clear_failed_logins(key: str) -> None:
    with _login_lock:
        _failed_login_attempts.pop(key, None)


def set_session_cookie(response: Response, username: str, config: AuthConfig) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        _sign_session(username, config),
        httponly=True,
        secure=config.cookie_secure,
        samesite="lax",
        max_age=config.session_ttl_seconds,
        path="/",
    )


def clear_session_cookie(response: Response, secure: bool = False) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def current_user(request: Request) -> str | None:
    try:
        config = load_auth_config()
    except HTTPException:
        return None
    return _verify_session(request.cookies.get(SESSION_COOKIE), config)


def require_user(request: Request) -> str:
    config = load_auth_config()
    username = _verify_session(request.cookies.get(SESSION_COOKIE), config)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
    return username


def _sign_session(username: str, config: AuthConfig) -> str:
    payload = {
        "u": username,
        "exp": int(time.time()) + config.session_ttl_seconds,
    }
    payload_text = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_b64 = _b64encode(payload_text.encode("utf-8"))
    signature = _session_signature(payload_b64, config.session_secret)
    return f"{payload_b64}.{signature}"


def _verify_session(cookie_value: str | None, config: AuthConfig) -> str | None:
    if not cookie_value or "." not in cookie_value:
        return None
    payload_b64, signature = cookie_value.rsplit(".", 1)
    expected_signature = _session_signature(payload_b64, config.session_secret)
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(_b64decode(payload_b64).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None

    username = payload.get("u")
    expires_at = payload.get("exp")
    if not isinstance(username, str) or not isinstance(expires_at, int):
        return None
    if expires_at < int(time.time()):
        return None
    if username not in config.users:
        return None
    return username


def _session_signature(payload_b64: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _parse_users(raw_users: str) -> dict[str, str]:
    raw_users = raw_users.strip()
    if not raw_users:
        return {}
    if raw_users.startswith("{"):
        try:
            parsed = json.loads(raw_users)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OFAC_AUTH_USERS is invalid JSON.",
            ) from exc
        if not isinstance(parsed, dict):
            return {}
        return {
            str(username).strip(): str(password_hash).strip()
            for username, password_hash in parsed.items()
            if str(username).strip() and str(password_hash).strip()
        }

    users: dict[str, str] = {}
    for item in raw_users.split(","):
        if "=" not in item:
            continue
        username, password_hash = item.split("=", 1)
        username = username.strip()
        password_hash = password_hash.strip()
        if username and password_hash:
            users[username] = password_hash
    return users


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _recent_attempts(key: str, now: float) -> list[float]:
    cutoff = now - LOGIN_ATTEMPT_WINDOW_SECONDS
    return [attempt for attempt in _failed_login_attempts.get(key, []) if attempt >= cutoff]


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
