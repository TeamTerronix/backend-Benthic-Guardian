"""
db_check.py — verify DATABASE_URL before starting the API (used in Docker entrypoint).
"""

from database import DATABASE_URL, check_database_connection, mask_database_url


def main() -> int:
    print(f"Checking database: {mask_database_url(DATABASE_URL)}")
    try:
        check_database_connection()
    except Exception as exc:
        print(f"DATABASE CONNECTION FAILED: {exc}")
        print(
            "On Render: set DATABASE_URL in Environment (Supabase session pooler URI, port 5432). "
            "URL-encode special characters in the password."
        )
        return 1
    print("Database connection OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
