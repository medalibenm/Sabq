"""Password hashing with Argon2id (argon2-cffi defaults, RFC 9106 low-memory profile)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_LENGTH = 10
MAX_LENGTH = 128

_hasher = PasswordHasher()
# Verified against when the email is unknown, so a wrong email takes as long as a wrong password.
_DUMMY_HASH = _hasher.hash("sabq-dummy-password-for-timing")


def policy_error(password: str) -> str | None:
    if len(password) < MIN_LENGTH:
        return f"password must be at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return f"password must be at most {MAX_LENGTH} characters"
    if not password.strip():
        return "password must not be only spaces"
    return None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
