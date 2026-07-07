"""
Password hashing utilities (bcrypt).

Used by the auth blueprint and the seed script. Never store or compare plaintext
passwords — always hash on write and verify on read.
"""

import bcrypt


def hash_password(password: str) -> str:
    """Return a bcrypt hash (utf-8 string) for the given plaintext password."""
    if password is None:
        raise ValueError("password must not be None")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Return True if the plaintext password matches the stored bcrypt hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed/legacy (non-bcrypt) hash — treat as a failed match, don't crash.
        return False
