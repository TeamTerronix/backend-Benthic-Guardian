#!/bin/sh
set -e

echo "Checking database connection..."
python db_check.py

echo "Creating database tables if needed..."
python create_tables.py

PORT="${PORT:-8000}"
echo "Starting SLIOT API on :${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
