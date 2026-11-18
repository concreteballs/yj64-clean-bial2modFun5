# YJ-64 Council — standalone server deployment

The repository contains a portable HTTP API and persistent worker. Both use one standard PostgreSQL database; neither requires Supabase at runtime.

## Components

- `cloud_worker/api.py` — FastAPI ingress implementing `yj64.council-api.v1`.
- `cloud_worker/worker.py` — persistent Council execution worker.
- `cloud_worker/queue_store.py` — Supabase compatibility and standard PostgreSQL adapters.
- `cloud_worker/postgres/schema.sql` — standalone database schema.
- `cloud_worker/compose.yaml` — API and worker containers using the same image and database.

The previous Supabase Edge Function remains a separate fallback deployment. Never connect a Supabase Edge Function to a PostgreSQL-backed worker, or the standalone API to a Supabase-backed worker: API and worker must share the same queue database.

## Free hosting target

Oracle Cloud Always Free ARM64 VM remains the primary candidate, subject to regional capacity and current account eligibility. The Docker image is built for both `linux/amd64` and `linux/arm64`. Google Cloud's small e2-micro free tier is a fallback for limited testing. Render Free is not suitable for a persistent worker.

Re-check official limits before creating an instance:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://render.com/docs/free
- https://render.com/docs/background-workers

## PostgreSQL preparation

The Compose stack includes PostgreSQL 16 with a persistent named volume. On first initialization, the database container creates a non-login schema owner, a separate restricted `yj64_runtime` role, applies `00-runtime-role.sql`, `schema.sql` and `02-runtime-grants.sql` in order, and grants the API/worker only the table and sequence privileges they need. The owner password is used only by the database container; the runtime password is used by API and worker. PostgreSQL is not published on a host port; only the API's loopback port is exposed.

Set a URL-safe random password (hex characters avoid connection-string escaping problems):

```sh
openssl rand -hex 32
```

Generate two different values. Put one in `YJ64_POSTGRES_OWNER_PASSWORD` and the other in `YJ64_POSTGRES_PASSWORD` in `.env`. Compose constructs the internal `DATABASE_URL` for both API and worker using the restricted runtime role and private service name `postgres`.

For an existing or externally managed PostgreSQL database, apply `cloud_worker/postgres/schema.sql` manually before starting API/worker and adjust the Compose `DATABASE_URL` environment expression for that database. Keep API and worker pointed at the exact same database.

## Configure and start

On the Linux VM:

```sh
git clone https://github.com/concreteballs/yj64-clean-bial2modFun5.git
cd yj64-clean-bial2modFun5/cloud_worker
cp .env.example .env
chmod 600 .env
```

Edit `.env` with the two generated database passwords and at least two real provider routes. The example contains placeholders only. The Compose file builds the internal database connection string; do not add a public database port. Keep these initial gate values unchanged:

```dotenv
YJ64_COUNCIL_ENGINE_ADAPTER=not_ready
YJ64_COUNCIL_WORKER_ENABLED=false
YJ64_QUEUE_BACKEND=postgres
```

Then start both services:

```sh
docker compose -f compose.yaml up -d --build
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs -f
```

The API binds only to `127.0.0.1:8080`. Put an HTTPS reverse proxy (for example, Caddy or Nginx) in front of it, enable request rate limiting, and expose only HTTPS publicly. Do not expose port 8080 directly. The worker has no inbound port.

Health endpoint: `GET http://127.0.0.1:8080/health`. It reports API/database status and whether a live worker heartbeat exists. The API may be healthy while request intake is intentionally disabled.

## Agent credentials

The API accepts bearer tokens whose SHA-256 hashes are stored in `yj64_council_api_agents.token_hash`. Generate a unique token on a trusted machine:

```sh
TOKEN="$(openssl rand -hex 32)"
printf '%s' "$TOKEN" | sha256sum
```

Insert the resulting 64-character hash using the runtime database role from the server: `docker compose exec -T postgres psql -U yj64_runtime -d yj64`. Example:

```sql
INSERT INTO public.yj64_council_api_agents (agent_id, token_hash, scopes, enabled)
VALUES (
  'your-agent-id',
  'PASTE_SHA256_HASH_HERE',
  ARRAY['council:submit', 'council:read', 'council:cancel'],
  true
);
```

Keep the raw token only in the authorized client secret store. Do not commit it, place it in a public file, or send it in chat. Disable an agent by setting `enabled = false`.

## API contract

All requests require `x-yj64-protocol-version: yj64.council-api.v1` and a bearer token with the corresponding scope.

- `POST /api/v1/external-agents/council/requests` — submit (also requires matching `Idempotency-Key` header).
- `GET /api/v1/external-agents/council/requests/{request_id}` — status.
- `GET /api/v1/external-agents/council/requests/{request_id}/result` — validated result.
- `POST /api/v1/external-agents/council/requests/{request_id}/cancel` — cancel.

The request intake gate is deliberately closed by default. Do not change either gate variable to `ready/true` until the API and worker share the same database, at least two real provider routes work, and authenticated submit → execute → status → result plus cancellation and lease-recovery tests have passed.

## Operations and migration

- Worker concurrency is bounded by `YJ64_WORKER_CONCURRENCY` (1–8).
- Leases are renewed while a task is running; expired leases can be reclaimed.
- PostgreSQL is the source of truth. Container filesystems are disposable.
- Back up PostgreSQL regularly and test restore before moving hosts.
- On a future paid VPS or self-hosted server, reuse the same OCI image and change only `DATABASE_URL`, provider secrets and reverse-proxy configuration.

## What CI proves

The workflow compiles the API and worker, runs deterministic engine/API tests, queue adapter tests, and PostgreSQL integration tests against a disposable PostgreSQL 16 service, then builds AMD64 and ARM64 OCI images. A passing CI run does not prove live provider credentials, server provisioning, HTTPS configuration, backups or production uptime.
