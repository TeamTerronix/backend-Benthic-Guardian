#!/bin/sh
# Native Python start (Render without Docker). From backend/ directory:
#   chmod +x start.sh && ./start.sh
set -e

python create_tables.py

PORT="${PORT:-8000}"
echo "Starting SLIOT API on :${PORT}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT}"
