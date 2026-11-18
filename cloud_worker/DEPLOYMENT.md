# YJ-64 Council Worker — deployment

The Council worker is a separate persistent Linux container. Do not run it inside the Android APK or a Supabase Edge Function.

## Current deployment model

The repository now contains a standalone FastAPI ingress (`cloud_worker/api.py`) and PostgreSQL worker adapter. The standalone Compose stack runs both containers against one PostgreSQL database. Keep the existing Supabase Edge Function deployment as a fallback until the standalone stack passes its full authenticated end-to-end acceptance test.

The worker routes persistence through `cloud_worker/queue_store.py`. The standalone API and worker both use `DATABASE_URL`; the worker selects `YJ64_QUEUE_BACKEND=postgres`. Do not run a PostgreSQL worker against the Supabase Edge Function or a Supabase worker against the standalone API: each pair must share one database. See [PORTABILITY.md](PORTABILITY.md).

## Hosting choice

- **Primary free candidate: Oracle Cloud Always Free VM.** The official Always Free allowance currently includes up to 2 OCPUs / 12 GB RAM equivalent for Ampere A1 and 200 GB total block storage. It is ARM64; build and verify the image for linux/arm64. Capacity is not guaranteed in every home region and idle compute may be reclaimed. Check current account limits before provisioning.
- **Secondary: Google Cloud e2-micro Free Tier.** One VM is free only in specified US regions, with 30 GB-month standard disk and 1 GB monthly outbound transfer. A billing account is required and overages are billable. It is a small test/fallback, not the preferred host.
- **Render Free is not suitable for the persistent worker.** Free Web Services sleep after 15 minutes, have no persistent disk and Render does not offer free Background Worker instances. A Render Background Worker requires a paid compute plan.

Always re-check provider limits at provisioning time:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.cloud.google.com/free/docs/free-cloud-features
- https://render.com/docs/free
- https://render.com/docs/background-workers

## Build and run

Build from repository root (Compose builds the same image for API and worker):

```sh
docker build -f cloud_worker/Dockerfile -t yj64-council-worker:latest .
```

On the Linux VM:

```sh
cd cloud_worker
cp .env.example .env
# Edit .env and insert real server-side credentials using a secure editor.
docker compose -f compose.yaml up -d --build
docker compose -f compose.yaml logs -f
```

Protect `.env`:

```sh
chmod 600 .env
```

Do not commit `.env`, copy it into a public artifact, or paste secrets into logs or chat. Use a host secret manager or root-readable environment file where available.

## Required runtime secrets

- `SUPABASE_URL`: current project URL.
- `SUPABASE_SERVICE_ROLE_KEY`: server-only service-role key.
- `YJ64_COUNCIL_PROVIDER_CONFIG`: JSON object with at least two configured provider routes.

The repository's `.env.example` contains placeholder values only. Real provider credentials must be provisioned separately.

Optional:
- `YJ64_WORKER_POLL_SECONDS` (default 3)
- `YJ64_WORKER_LEASE_SECONDS` (default 180; allowed 60–900)
- `YJ64_WORKER_ID` (generated uniquely if omitted)
- `YJ64_WORKER_CONCURRENCY` (default 2; bounded 1–8)

## Activation sequence

1. Provision a Linux VM and restrict inbound firewall rules. The worker itself needs no public inbound port.
2. Install Docker Engine and the Compose plugin from the OS vendor's supported packages.
3. Add secrets to the host; set file permissions to owner-only.
4. Start exactly one worker instance initially.
5. Confirm logs show the worker ready message and the Supabase table `yj64_council_api_workers` receives fresh heartbeats.
6. Confirm API health reports a live worker.
7. Run a controlled authenticated test with real provider routes, then test cancellation, lease recovery and terminal result persistence.
8. Keep the API submit gate closed until the entire live E2E lifecycle is verified.

Do not enable `YJ64_COUNCIL_ENGINE_ADAPTER=ready` or `YJ64_COUNCIL_WORKER_ENABLED=true` before the worker heartbeat, real provider E2E, cancellation, lease recovery and result persistence are verified.

## Standalone PostgreSQL backend

The standalone API always uses `DATABASE_URL`; the worker uses that same value with `YJ64_QUEUE_BACKEND=postgres`. Apply `cloud_worker/postgres/schema.sql` before starting either service. The old Supabase Edge Function remains a separate deployment path and must only be paired with the Supabase-backed worker.

## Moving to paid or self-hosted infrastructure

The same OCI image and environment contract should be reused. Export PostgreSQL, restore into the target PostgreSQL instance, verify row counts and representative task histories, then switch `DATABASE_URL`. Do not couple application logic to Oracle, Google Cloud, Render or any host-specific API.

## What CI proves

The Council Worker CI workflow compiles the router, worker and API; runs deterministic engine/API tests plus queue and HTTP contract integration tests against disposable PostgreSQL 16; and builds AMD64 and ARM64 OCI images. A passing run validates the tested contracts, not real provider credentials, cloud provisioning, billing, backups or production uptime.
