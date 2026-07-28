"""Unit tests for auth helpers (no HTTP)."""

from auth import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("coral-secret")
    assert hashed != "coral-secret"
    assert verify_password("coral-secret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_password_rejects_garbage_hash():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_access_token_roundtrip():
    token = create_access_token(user_id=42)
    data = decode_access_token(token)
    assert data.user_id == 42
