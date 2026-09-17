# Deploying OpenTerminalUI with Coolify

Deploys the terminal to a VPS behind Coolify's proxy, on PostgreSQL 16, with automatic HTTPS.

Uses **`docker-compose.coolify.yml`**, not the upstream `docker-compose.yml`. The upstream file targets a
laptop and is unsafe on a public VPS — see the header comments in that file for the four specific reasons.

## 1. Create the resource

In Coolify: **New Resource → Docker Compose**, source = this repository, branch `main`,
**Docker Compose Location** = `docker-compose.coolify.yml`.

## 2. Set environment variables

Paste every variable from your generated `.env.coolify.local` into Coolify's **Environment Variables** tab.

Secrets use the `${VAR:?...}` form, so a missing one **fails the deploy with a message naming the variable**
rather than silently starting with an upstream default. Required:

| Variable | Notes |
|---|---|
| `OPENTERMINALUI_ENV` | Must be `production`. Makes `backend/db/base.py` refuse to run on SQLite — this is what guarantees Postgres is actually in use. |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@postgres:5432/dbname`. Host is `postgres` (compose service name). |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Must match `DATABASE_URL`. Never keep the upstream default password. |
| `REDIS_URL` / `REDIS_PASSWORD` | `redis://:pass@redis:6379/0`. Password must match. |
| `JWT_SECRET_KEY`, `CACHE_SIGNING_KEY` | `openssl rand -hex 32` each. |
| `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` | **Without these you cannot log in.** `scripts/seed_admin.py` no-ops when unset and never reports it. Leave them set: the seed is idempotent and no-ops once a user exists. |
| `OPENTERMINALUI_CORS_ORIGINS` | `https://your-domain`. The default is `localhost:5173` and will block the browser. |

Market-data and AI keys (`FMP_API_KEY`, `FINNHUB_API_KEY`, `KITE_*`, `OPENROUTER_API_KEY`, …) are optional;
the app falls back to built-in providers.

## 3. Domain and TLS

Point an A record at the VPS IP, then set the domain on the **`backend`** service in Coolify with target
port **8000**. Coolify's proxy requests the Let's Encrypt certificate automatically.

The compose file publishes **no** host ports by design. Reaching the app is the proxy's job.

## 4. Firewall

Allow only **22, 80, 443**. Ports 5432 and 6379 must not be reachable from outside — that is the whole point
of removing upstream's port mappings.

## 5. Deploy

Watch the logs for, in order: frontend Vite build → `alembic upgrade head` →
`[seed-admin] created initial admin account:` → `Uvicorn running on 0.0.0.0:8000`.

If you see `[seed-admin] ... skipping`, your `BOOTSTRAP_ADMIN_*` values did not reach the container.

## Verification

1. `https://<domain>/health` responds.
2. Log in with `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.
3. Confirm Postgres is genuinely in use — not a silent fallback:
   `docker exec <postgres-container> psql -U openterminalui -d openterminalui -c '\dt'`
   should list alembic-created tables.
4. **From your own machine, not the VPS**, confirm the datastores are closed:
   `nc -vz <vps-ip> 5432` and `nc -vz <vps-ip> 6379` must both be refused.
5. Load a chart and the screener (exercises Redis and the data adapters).
6. `curl -I http://<domain>` redirects to HTTPS with a valid certificate.

## Notes

- Uvicorn runs a **single worker** (`backend/entrypoint.sh`). If it is slow under load, that is the first
  thing to raise.
- Back up Postgres on a schedule (`pg_dump`) via Coolify's scheduled tasks.
- To pull upstream changes: this file and `docker-compose.coolify.yml` are additions, so
  `git pull upstream main` merges cleanly.
