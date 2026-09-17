# Deploying OpenTerminalUI with Coolify

Deploys the terminal behind Coolify's proxy on a Coolify-managed PostgreSQL 16 resource, with
automatic HTTPS. Same VPS and same pattern as `landanalysis`.

Uses **`docker-compose.coolify.yml`**, not the upstream `docker-compose.yml`. The upstream file targets
a laptop and fails four ways on a public VPS — the header comments in that file give the specifics.

## 1. Create the PostgreSQL resource first

In Coolify: **New Resource → Database → PostgreSQL 16**, on the same server and project.

The app owns its schema (`backend/entrypoint.sh` runs `alembic upgrade head` on every boot), so the
database needs no init scripts. Plain `postgres` is fine — no PostGIS, unlike `landanalysis`.

Copy its **internal** connection URL. Then **check the scheme**: it must read `postgresql+asyncpg://`.
If Coolify gives you `postgres://`, rewrite it — `backend/db/base.py` only normalises `postgresql://`,
and SQLAlchemy rejects `postgres://` outright. This is the single easiest way to break the deploy.

Turn on scheduled backups while you are there. That is the entire reason the database lives outside
the compose file.

## 2. Create the application resource

**New Resource → Docker Compose**, source = this repository, branch `main`,
**Docker Compose Location** = `docker-compose.coolify.yml`.

## 3. Set environment variables

Paste everything from your generated `.env.coolify.local` into Coolify's **Environment Variables** tab.

Secrets use the `${VAR:?...}` form, so a missing one **fails the deploy naming the variable** rather
than silently starting on an upstream default.

| Variable | Notes |
|---|---|
| `OPENTERMINALUI_ENV` | Must be `production`. Makes `backend/db/base.py` refuse SQLite — this is what proves Postgres is really in use. |
| `DATABASE_URL` | The managed resource's internal URL, scheme `postgresql+asyncpg://`. |
| `REDIS_URL` / `REDIS_PASSWORD` | `redis://:pass@redis:6379/0`. Password must match. Redis runs in the compose file. |
| `JWT_SECRET_KEY`, `CACHE_SIGNING_KEY` | `openssl rand -hex 32` each. |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` | **Without these you cannot log in.** `scripts/seed_admin.py` no-ops when unset and never reports it. Leave them set — the seed is idempotent once a user exists. |
| `OPENTERMINALUI_CORS_ORIGINS` | `https://your-domain`. The default is `localhost:5173` and will block the browser. |

Market-data and AI keys (`FMP_API_KEY`, `FINNHUB_API_KEY`, `KITE_*`, `OPENROUTER_API_KEY`, …) are
optional; the app falls back to built-in providers.

## 4. Domain and TLS

Point an A record at the VPS, then set the domain on the **`app`** service in Coolify with target port
**8000**. Coolify's proxy requests the Let's Encrypt certificate automatically.

The compose file publishes **no** host ports by design — reaching the app is the proxy's job.

## 5. Deploy

Deployment is a `git push` to `main`: Coolify watches the repository and rebuilds.

Watch the logs for, in order: Vite frontend build → `alembic upgrade head` →
`[seed-admin] created initial admin account:` → `Uvicorn running on 0.0.0.0:8000`.

`[seed-admin] ... skipping` means your `BOOTSTRAP_ADMIN_*` values never reached the container.

## Verification

1. `https://<domain>/health` responds.
2. Log in with `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.
3. Confirm the managed Postgres is really in use — tables should exist after the first boot:
   `\dt` via Coolify's database terminal should list alembic-created tables.
4. **From your own machine, not the VPS**, confirm nothing new is exposed:
   `nc -vz <vps-ip> 6379` must be refused.
5. Load a chart and the screener (exercises Redis and the data adapters).
6. `curl -I http://<domain>` redirects to HTTPS with a valid certificate.
7. Check `landanalysis` still responds — you have just added a second stack to its VPS.

## Notes

- Uvicorn runs a **single worker** (`backend/entrypoint.sh`). If it is slow under load, raise that first.
- To pull upstream changes: this file and `docker-compose.coolify.yml` are additions, so
  `git pull upstream main` merges cleanly.
