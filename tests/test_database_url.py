"""Unit tests for DATABASE_URL helpers."""

from database import is_supabase_url, mask_database_url, normalize_database_url


def test_normalize_postgres_schemes():
    assert normalize_database_url("postgres://u:p@host/db").startswith("postgresql+psycopg://")
    assert normalize_database_url("postgresql://u:p@host/db").startswith("postgresql+psycopg://")
    assert normalize_database_url("postgresql+psycopg://u:p@host/db").startswith(
        "postgresql+psycopg://"
    )


def test_normalize_strips_quotes_and_whitespace():
    assert normalize_database_url('  "sqlite:///./x.db"  ') == "sqlite:///./x.db"


def test_is_supabase_url():
    assert is_supabase_url("postgresql://x@db.abcdefgh.supabase.co:5432/postgres") is True
    assert is_supabase_url("postgresql://x@aws-0-us-east-1.pooler.supabase.com:5432/postgres") is True
    assert is_supabase_url("postgresql://x@localhost:5432/postgres") is False


def test_mask_database_url_hides_password():
    masked = mask_database_url("postgresql+psycopg://user:s3cret@db.example.com:5432/app")
    assert "s3cret" not in masked
    assert "***" in masked
    assert "user" in masked
    assert "db.example.com" in masked
