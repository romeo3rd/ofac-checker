from __future__ import annotations

import getpass
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from backend.app.auth import hash_password  # noqa: E402


def main() -> int:
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    if len(password) < 14:
        print("Use at least 14 characters.", file=sys.stderr)
        return 1

    print(hash_password(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
