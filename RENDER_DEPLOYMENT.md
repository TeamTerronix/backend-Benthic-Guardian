# SLIOT Backend — Render Deployment Guide

This guide is for deploying the **SLIOT FastAPI backend** to [Render](https://render.com).

The **database is already set up on Supabase** (tables + test data). The **dashboard** stays on **Vercel**.

You only need the **backend GitHub repo** (`TeamTerronix/backend`). You do **not** need the full monorepo.

---

## What you are deploying

| Piece | Where it runs | Status |
|-------|----------------|--------|
| API (FastAPI + PINN forecasts) | **Render** (Docker) | You are setting this up |
| Database (Postgres) | Supabase | **Already done** |
| Dashboard (Next.js) | Vercel | **Already deployed** |
| ESP32 sensors | POST to Render API URL | Update after deploy |

---

## Before you start

Get these from the team (do **not** commit secrets to Git):

- [ ] **`DATABASE_URL`** — existing Supabase connection string
- [ ] **`SECRET_KEY`** — same value used in the team’s backend `.env`
- [ ] **Vercel dashboard URL** — for `CORS_ORIGINS` (e.g. `https://something.vercel.app`)
- [ ] Access to the **backend** GitHub repo
- [ ] A [Render](https://render.com) account (team/org access)

**Plan note:** Use Render **Starter** ($7/mo) or higher. The free tier is too small for TensorFlow + PINN and may crash on forecast jobs.

---

## Step 1 — Check the backend repo has model files

The API needs PINN files inside **`model/`** in the backend repo:

```
model/
  forecaster.py
  utils.py
  pinn_model_best.h5
  scalers.pkl
  sensor_info.pkl
  sliot_dataset/
  prediction_results.csv   (optional)
  training_history.csv     (optional)
```

If `model/pinn_model_best.h5` is missing, ask the team to run locally:

```bash
cd backend
python sync_model_assets.py
git add model/
git commit -m "Add PINN runtime assets"
git push
```

---

## Step 2 — Deploy on Render

### Option A — Blueprint (easiest)

1. Render → **New** → **Blueprint**.
2. Connect the **backend** GitHub repo.
3. Render reads `render.yaml` from the repo root.
4. When asked for secrets, set:
   - **`DATABASE_URL`** — from the team (Supabase URI, already configured)
   - **`CORS_ORIGINS`** — Vercel dashboard URL, e.g. `https://your-app.vercel.app`
5. Click **Apply** and wait for the build (first build can take **10–20 minutes** because of TensorFlow).

### Option B — Manual Web Service

1. Render → **New** → **Web Service**.
2. Connect the **backend** repo.
3. Settings:

   | Field | Value |
   |-------|--------|
   | **Name** | `sliot-backend` (or any name) |
   | **Region** | Singapore (closest to Sri Lanka) |
   | **Branch** | `main` |
   | **Runtime** | **Docker** |
   | **Root Directory** | *(leave empty)* |
   | **Dockerfile Path** | `./Dockerfile` |
   | **Instance Type** | **Starter** or higher |
   | **Health Check Path** | `/` |

4. **Environment** → add variables:

   | Key | Value |
   |-----|--------|
   | `DATABASE_URL` | From the team |
   | `SECRET_KEY` | From the team (must match what was used for existing users) |
   | `ALGORITHM` | `HS256` |
   | `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` |
   | `CORS_ORIGINS` | `https://your-dashboard.vercel.app` |
   | `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` |

5. **Create Web Service** and wait for deploy.

On startup, the container runs `create_tables.py` automatically (safe if tables already exist).

---

## Step 3 — Verify the API

When deploy is green, open:

- Health: `https://YOUR-SERVICE.onrender.com/`
- Docs: `https://YOUR-SERVICE.onrender.com/docs`

Health should return JSON with `"status": "ok"`.

Test sensor ingest (sensor `1` should already exist in the database):

```bash
curl -X POST "https://YOUR-SERVICE.onrender.com/data" \
  -H "Content-Type: application/json" \
  -d "{\"sensor_uid\":\"1\",\"temperature\":29.0}"
```

Test dashboard login (default prototype user, if the team provisioned it):

- Email: `prototype@sliot.local`
- Password: `proto123`

---

## Step 4 — Connect the Vercel dashboard

Full steps: see dashboard repo **`CONNECT_BACKEND.md`**.

**Vercel** → Environment:

```env
NEXT_PUBLIC_API_URL=https://backend-benthic-guardian.onrender.com
```

Redeploy the dashboard after saving.

**Render** → Environment (required for browser login from Vercel):

```env
CORS_ORIGINS=https://YOUR-DASHBOARD.vercel.app
CORS_ORIGIN_REGEX=https://.*\.vercel\.app
```

Replace `YOUR-DASHBOARD.vercel.app` with your real Vercel URL.

---

## Step 5 — Update ESP32 firmware (if used)

Devices must POST to the Render URL, not localhost or old EC2:

```text
https://YOUR-SERVICE.onrender.com/data
```

Body (JSON):

```json
{"sensor_uid":"1","temperature":29.0}
```

`sensor_uid` must match an **approved** sensor in the database.

---

## Architecture

```
ESP32  ──POST /data──►  Render (FastAPI + PINN)
                              │
                              ▼
                         Postgres (existing)
                              ▲
Vercel dashboard  ──HTTPS API──┘
```

---

## Troubleshooting

### Database not connected on Render (most common)

The Docker image **does not include** `backend/.env`. You must set **`DATABASE_URL` in Render → Environment**.

If `DATABASE_URL` is missing, the app used to silently fall back to **SQLite inside the container** (empty, not your Supabase data).

After redeploying with the fix, check:

```text
https://YOUR-SERVICE.onrender.com/
```

Response should include `"database": "ok"`. If `"database": "error"`, fix `DATABASE_URL` on Render.

**Correct value** (from team — Supabase session pooler, port **5432**):

```env
DATABASE_URL=postgresql+psycopg://postgres.pzjcvokjqvgbrrcrxipn:URL_ENCODED_PASSWORD@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres
```

Rules:

- No quotes around the value in Render
- Password special chars must be URL-encoded (`&` → `%26`, `!` → `%21`, `+` → `%2B`)
- Use **session pooler (5432)**, not transaction (6543), unless you know you need it
- `SECRET_KEY` on Render must match the key used when users were created in Supabase

### Build fails on Render

- Confirm **`model/pinn_model_best.h5`** exists in the repo.
- Check build logs for missing files or pip errors.
- First Docker build is slow (TensorFlow download) — wait 15–20 min.

### `Application failed to respond` / health check fails

- Check logs in Render → **Logs**.
- Often: wrong `DATABASE_URL` or `SECRET_KEY` on Render.
- Ask the team to confirm the connection string still works.

### Dashboard login works locally but not on Vercel

- Set `CORS_ORIGINS` on Render to the **exact** Vercel URL (`https://...`).
- `SECRET_KEY` on Render must be the **same** key used when users were created.
- Redeploy Render after changing env vars.

### `POST /data` returns 404 or 403

- `sensor_uid` in JSON must match an approved sensor in the database.
- Ask the team to run `provision_prototype.py` if no sensors exist.

### Forecast / PINN errors in logs

- Missing files in `model/` — re-run `sync_model_assets.py` and push.
- Out of memory on free tier — upgrade to **Starter**.

### Cold starts (slow first request)

- Render may spin down after idle; first request can take 30–60+ seconds.

---

## Updating the deployment

| Change | What to do |
|--------|------------|
| Backend code | `git push` to `main` → Render auto-redeploys |
| New PINN weights | `python sync_model_assets.py` → commit `model/` → push |
| New env var | Render → Environment → save → redeploy |
| New dashboard URL | Update `CORS_ORIGINS` on Render + `NEXT_PUBLIC_API_URL` on Vercel |

---

## Quick checklist

- [ ] `DATABASE_URL` and `SECRET_KEY` from team set on Render
- [ ] `CORS_ORIGINS` = Vercel dashboard URL
- [ ] `https://YOUR-SERVICE.onrender.com/docs` opens
- [ ] `POST /data` test succeeds
- [ ] Vercel `NEXT_PUBLIC_API_URL` points to Render
- [ ] Dashboard login works on production URL
- [ ] ESP32 (if any) points to Render `/data`

---

## Who to ask

- **`DATABASE_URL` / `SECRET_KEY`** — team lead  
- **Vercel dashboard URL** — frontend owner  
- **Sensor UIDs / field devices** — hardware team  
- **PINN model files** — ML team (`sync_model_assets.py`)

---

## Related files in this repo

| File | Purpose |
|------|---------|
| `Dockerfile` | Production Docker image |
| `render.yaml` | Render Blueprint config |
| `docker-entrypoint.sh` | Creates tables + starts uvicorn on `$PORT` |
| `sync_model_assets.py` | Copy PINN files into `model/` |
| `.env.example` | Local env template |
| `README.md` | General backend development setup |
