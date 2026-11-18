# Portability contract

The Council engine is the application layer. Hosting, queue transport, database access and ingress are adapters.

## Stable core

The following must not import or depend on a cloud vendor SDK:

- Council task orchestration and participant lifecycle.
- Provider-neutral result schema and diagnostic event envelope.
- Retry/idempotency rules and bounded execution limits.
- Provider router contract in `llm_api.py`.

The engine may receive dependencies through constructor arguments/callbacks. It must not read Android app paths, Android APIs, host metadata APIs or provider credentials from source files.

## Replaceable adapters

| Boundary | Current implementation | Portable replacement |
|---|---|---|
| HTTP ingress | Portable FastAPI `cloud_worker/api.py`; Supabase Edge Function retained as fallback | Same API container behind any HTTPS reverse proxy |
| Queue and task state | PostgreSQL `PostgresQueueStore`; Supabase adapter retained as fallback | Standard PostgreSQL with `FOR UPDATE SKIP LOCKED` |
| Worker registry | PostgreSQL worker table and heartbeat; Supabase compatibility adapter | PostgreSQL table and heartbeat |
| Provider access | Shared `llm_api.py` router | Keep same router; inject route config from secrets |
| Durable files | No authoritative worker-local storage | PostgreSQL metadata + optional S3-compatible object storage |

The worker depends on the `QueueStore` protocol in `cloud_worker/queue_store.py`. `SupabaseQueueStore` preserves the current PostgREST/RPC behavior; `PostgresQueueStore` uses the standalone PostgreSQL schema and atomic row locking. The portable FastAPI ingress in `cloud_worker/api.py` implements the existing public JSON contract against that same PostgreSQL database. The standalone deployment is now code-complete at the adapter/API layer, but remains gated on CI and authenticated end-to-end verification.

## Configuration contract

- Runtime: Python 3.11 or newer.
- Image: OCI/Docker image, multi-platform `linux/amd64` and `linux/arm64`.
- Configuration: environment variables or mounted secret files.
- API: HTTPS + JSON.
- Database target: PostgreSQL-compatible SQL.
- Shutdown: SIGTERM/SIGINT, stop claiming new work, allow bounded in-flight completion, release/expire leases safely.
- Persistence: database is authoritative; container filesystem is disposable.
- Deployment: Docker Compose for a single VM; same image may be scheduled by another orchestrator later.

## Migration order

1. [x] Keep the existing Supabase-backed deployment available as the fallback path.
2. [x] Extract current Supabase calls from `worker.py` into a `QueueStore` interface and preserve behavior with a Supabase implementation.
3. [x] Add a PostgreSQL implementation using atomic claim transactions (`FOR UPDATE SKIP LOCKED`), lease renewal, cancellation, progress, terminal-state writes and worker heartbeat. Standalone schema: `postgres/schema.sql`.
4. [x] Add PostgreSQL integration tests for concurrent claims, expired-lease recovery, cancellation and result persistence.
5. [x] Containerize the HTTP ingress behind the existing API contract; CI exercises submit, idempotency, status and cancellation against disposable PostgreSQL.
6. Verify CI, provision and restore a real database backup, then perform authenticated provider E2E before opening intake.

## Provider portability acceptance tests

A release is not called portable until:

- The same image starts on amd64 and arm64.
- The same queue contract tests pass against Supabase and standard PostgreSQL adapters.
- A queued task survives worker/container restart.
- Expired leases are recovered without duplicate terminal results.
- SIGTERM does not lose acknowledged task state.
- PostgreSQL export restores into an independent PostgreSQL instance.
- No vendor-specific secret, SDK or URL is required by the Council engine.
