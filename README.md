# SLIOT Backend

FastAPI backend for temperature monitoring, predictions, auth, and scheduled jobs.

**Deploying to production?** See **[RENDER_DEPLOYMENT.md](./RENDER_DEPLOYMENT.md)** — Render deploy guide (database already on Supabase).

## Prerequisites

- Python 3.10+ (3.11 recommended)
- Git
- Optional: PostgreSQL (if you do not want to use local SQLite)

## 1. Clone the Repository

```bash
git clone https://github.com/TeamTerronix/backend.git
cd backend
```

## 2. Create and Activate a Virtual Environment

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### Windows (CMD)

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure Environment Variables

Create a `.env` file from the sample:

```bash
cp .env.example .env
```

If `cp` is not available on Windows CMD, use:

```cmd
copy .env.example .env
```

Update `.env` values as needed:

- `DATABASE_URL`
- `SECRET_KEY`
- `ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`

On a server (EC2), set `DATABASE_URL` to your **PostgreSQL / RDS** URL before running scripts or `uvicorn`, or tools will default to **local SQLite** (`./sliot.db`) and you will not see data in RDS.

### Database options

- **Supabase (recommended for production)**  
  1. Create a project at [supabase.com](https://supabase.com)  
  2. **Project Settings → Database → Connection string → URI** (Session pooler, port `5432`)  
  3. Put it in `backend/.env` as `DATABASE_URL` (use `postgresql+psycopg://…`; URL-encode special characters in the password)  
  4. Create tables and migrate existing data:
     ```bash
     python migrate_to_supabase.py --source sqlite:///./sliot.db
     ```
  5. Run the API with the same `DATABASE_URL`

- SQLite (default, easiest local setup):
  - `DATABASE_URL=sqlite:///./sliot.db`
- PostgreSQL (local Docker or RDS):
  - `DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/sliot`

## 5. Create Database Tables

Run once after setting `DATABASE_URL`:

```bash
python create_tables.py
```

For **Supabase**, you can use `create_tables.py` or `migrate_to_supabase.py` (creates schema + copies data from SQLite).

## 5a. Migrate to Supabase

If you already have data in local SQLite (or another Postgres URL):

```bash
# 1. Set DATABASE_URL in .env to your Supabase URI
# 2. Copy data:
python migrate_to_supabase.py --source sqlite:///./sliot.db

# Re-run on same target (replace all rows):
python migrate_to_supabase.py --source sqlite:///./sliot.db --wipe-target
```

## 5b. (Schema updates) Run migrations scripts when needed

If you pull changes that add new columns (example: `network_group_id`), run:

```bash
python migrate_add_network_group_id.py
```

If ingest was changed from hourly to every sample, drop the old unique constraint:

```bash
python migrate_drop_sensor_readings_hourly_unique.py
```

## 5c. (Optional) Seed the Database with Test Data

If you want test users/sensors/readings/predictions in your PostgreSQL DB for dashboard testing:

```bash
python seed_data.py
```

## 5c. Prototype sensor + user (ESP32 / field devices)

Registers one dashboard user, one network, and one **approved** sensor so devices can `POST /data`.

```bash
python provision_prototype.py --sensor-uid "1"
```

Defaults: `prototype@sliot.local` / `proto123`. If login fails for an **existing** user, reset the password:

```bash
python provision_prototype.py --reset-password --user-password proto123
```

`provision_prototype.py` loads `backend/.env` **before** connecting, so `DATABASE_URL` in `.env` applies to provisioning.

## 5d. Sensor ingest (`POST /data`)

Devices send JSON to **`POST /data`** (no JWT). The body must include `sensor_uid` and `temperature`. `timestamp` is **optional**; if omitted, the server uses current UTC. **Each POST inserts one row** in `sensor_readings` (no hourly deduplication).

If you upgraded from an older DB that had hourly uniqueness, run once:

```bash
python migrate_drop_sensor_readings_hourly_unique.py
```

Example:

```bash
curl -sS -X POST "http://127.0.0.1:8000/data" \
  -H "Content-Type: application/json" \
  -d '{"sensor_uid":"1","temperature":29.0}'
```

`sensor_uid` must match a **registered and approved** sensor (see `provision_prototype.py`). OpenAPI: `/docs` → `POST /data`.

ESP32: `reciever_single_temp.ino` POSTs to `/data` with sensor id + temperature only; time is stored on the server.

## 6. Run the API

```bash
uvicorn main:app --reload --env-file .env
```

Server will start at:

- `http://127.0.0.1:8000`
- Swagger docs: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## 7. Deploy on Render (backend repo only)

Connect your **backend** GitHub repo directly — no monorepo required.

### Prerequisites

The repo must include **`model/`** with PINN runtime files (`pinn_model_best.h5`, `scalers.pkl`, etc.).

If you develop in the monorepo, sync before push:

```bash
python sync_model_assets.py
git add model/
git commit -m "Sync PINN runtime assets"
```

### Render settings

| Setting | Value |
|---------|--------|
| Runtime | Docker |
| Root Directory | *(leave empty — repo root)* |
| Dockerfile Path | `./Dockerfile` |
| Health Check | `/` |
| Plan | **Starter**+ (TensorFlow) |

Or use **`render.yaml`** in this repo (Blueprint deploy).

**Environment variables:** `DATABASE_URL` (Supabase), `SECRET_KEY`, `CORS_ORIGINS` (Vercel URL).

### After deploy

1. Vercel: `NEXT_PUBLIC_API_URL=https://<service>.onrender.com`
2. ESP32: `POST https://<service>.onrender.com/data`
3. `python provision_prototype.py --sensor-uid "1"` (local, against Supabase)

## Notes

- Background scheduler jobs start automatically with the app (see `scheduler.py`).
- `.env` is ignored by Git through `.gitignore`.
- PINN assets live in **`backend/model/`** (standalone repo) or sibling **`../model`** (monorepo). Override with `MODEL_DIR` if needed.

## Quick Health Check

After starting the server:

```bash
curl http://127.0.0.1:8000/
```

Expected response includes `status: "ok"`.
