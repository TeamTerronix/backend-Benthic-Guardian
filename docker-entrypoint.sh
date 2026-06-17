#!/bin/sh
set -e

cd /app/backend

echo "Creating database tables if needed..."
python create_tables.py

echo "Starting SLIOT API on :8000"
exec uvicorn main:app --host 0.0.0.0 --port 8000
