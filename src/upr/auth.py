"""Lightweight authentication & role-based capabilities.

Designed for an internal tool: a small YAML user store with salted PBKDF2
password hashes and three roles. Auth is *optional* — if no user store is
configured the app runs open (single-team prototype); once a store exists the
dashboard gates actions by role.

Roles and what they can do:
    viewer  — view dashboard, trends, reports
    analyst — viewer + import data, run scenarios, save snapshots
    admin   — analyst + manage mapping config / users

User store (``config/users.yaml``, path overridable via ``UPR_USERS_FILE``):

    users:
      - username: pfarmer
        name: Patrick Farmer
        role: admin
        salt: "<hex>"
        password_hash: "<hex>"

Generate an entry:  python -m upr.auth add pfarmer "Patrick Farmer" admin
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

_ITERATIONS = 200_000

CAPABILITIES: dict[str, set[str]] = {
    "viewer": {"view"},
    "analyst": {"view", "import", "scenario", "snapshot"},
    "admin": {"view", "import", "scenario", "snapshot", "admin"},
}


@dataclass(frozen=True)
class User:
    username: str
    name: str
    role: str
    salt: str = ""
    password_hash: str = ""

    @property
    def capabilities(self) -> set[str]:
        return CAPABILITIES.get(self.role, set())

    def can(self, capability: str) -> bool:
        return capability in self.capabilities


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) using PBKDF2-HMAC-SHA256."""
    salt_hex = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), _ITERATIONS
    )
    return salt_hex, digest.hex()


def verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    if not salt_hex or not expected_hash:
        return False
    _, computed = hash_password(password, salt_hex)
    return hmac.compare_digest(computed, expected_hash)


def make_user_record(username: str, name: str, role: str, password: str) -> dict:
    """Build a YAML-ready user dict with a fresh salted hash."""
    if role not in CAPABILITIES:
        raise ValueError(f"Unknown role {role!r}; choose {sorted(CAPABILITIES)}")
    salt, pw_hash = hash_password(password)
    return {
        "username": username, "name": name, "role": role,
        "salt": salt, "password_hash": pw_hash,
    }


def load_users(path: str) -> dict[str, User]:
    """Load the user store into {username: User}."""
    import yaml  # lazy import

    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    users: dict[str, User] = {}
    for raw in data.get("users", []):
        u = User(
            username=raw["username"], name=raw.get("name", raw["username"]),
            role=raw.get("role", "viewer"), salt=raw.get("salt", ""),
            password_hash=raw.get("password_hash", ""),
        )
        users[u.username] = u
    return users


def users_file_path() -> str | None:
    """Resolve the configured user store, or None if auth is disabled."""
    env = os.getenv("UPR_USERS_FILE")
    if env:
        return env if Path(env).is_file() else None
    default = Path("config/users.yaml")
    return str(default) if default.is_file() else None


def auth_enabled() -> bool:
    return users_file_path() is not None


def authenticate(username: str, password: str, users: dict[str, User]) -> User | None:
    """Return the User on valid credentials, else None."""
    user = users.get(username)
    if user is None:
        return None
    if verify_password(password, user.salt, user.password_hash):
        return user
    return None


def _cli(argv: list[str] | None = None) -> int:
    """`python -m upr.auth add <username> <name> <role>` -> prints a YAML entry."""
    import getpass
    import sys

    import yaml

    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 4 or argv[0] != "add":
        print('usage: python -m upr.auth add <username> "<name>" <role>')
        return 2
    _, username, name, role = argv[0], argv[1], argv[2], argv[3]
    pw = getpass.getpass("Password: ")
    record = make_user_record(username, name, role, pw)
    print(yaml.safe_dump({"users": [record]}, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
