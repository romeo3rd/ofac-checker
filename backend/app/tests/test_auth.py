from __future__ import annotations

from fastapi import HTTPException

from backend.app import auth


def test_password_hash_verification() -> None:
    stored_hash = auth.hash_password("correct horse battery staple")

    assert auth.verify_password("correct horse battery staple", stored_hash)
    assert not auth.verify_password("wrong password", stored_hash)


def test_parse_comma_separated_users(monkeypatch) -> None:
    stored_hash = auth.hash_password("correct horse battery staple")
    monkeypatch.setenv("OFAC_AUTH_USERS", f"admin={stored_hash}")
    monkeypatch.setenv("OFAC_SESSION_SECRET", "x" * 48)

    config = auth.load_auth_config()

    assert config.users == {"admin": stored_hash}


def test_missing_auth_config_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("OFAC_AUTH_USERS", raising=False)
    monkeypatch.delenv("OFAC_SESSION_SECRET", raising=False)

    try:
        auth.load_auth_config()
    except HTTPException as exc:
        assert exc.status_code == 503
    else:
        raise AssertionError("Expected missing auth config to fail closed")


def test_signed_session_round_trip() -> None:
    stored_hash = auth.hash_password("correct horse battery staple")
    config = auth.AuthConfig(
        users={"admin": stored_hash},
        session_secret="x" * 48,
        cookie_secure=False,
        session_ttl_seconds=3600,
    )

    cookie = auth._sign_session("admin", config)

    assert auth._verify_session(cookie, config) == "admin"
    assert auth._verify_session(f"{cookie}tampered", config) is None


def test_login_rate_limit_blocks_repeated_failures() -> None:
    key = "127.0.0.1:admin"
    auth._failed_login_attempts.clear()

    try:
        for _ in range(auth.MAX_FAILED_LOGIN_ATTEMPTS):
            auth.check_login_rate_limit(key)
            auth.record_failed_login(key)

        try:
            auth.check_login_rate_limit(key)
        except HTTPException as exc:
            assert exc.status_code == 429
        else:
            raise AssertionError("Expected repeated login failures to be rate limited")
    finally:
        auth._failed_login_attempts.clear()
