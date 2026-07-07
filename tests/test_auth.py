"""Tests for password hashing / verification."""

from app.security import hash_password, verify_password


def test_hash_verify_roundtrip():
    h = hash_password("s3cret-pw")
    assert h != "s3cret-pw"  # never store plaintext
    assert verify_password("s3cret-pw", h) is True


def test_wrong_password_fails():
    h = hash_password("correct")
    assert verify_password("wrong", h) is False


def test_empty_and_malformed_inputs_are_safe():
    assert verify_password("", hash_password("x")) is False
    assert verify_password("x", "") is False
    assert verify_password("x", "not-a-bcrypt-hash") is False
