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
| HTTP ingress | Supabase Edge Function `council-api` | Containerized HTTP API with the same JSON contract |
| Queue and task state | Supabase PostgREST + RPC | PostgreSQL adapter using standard SQL transactions and row locking |
| Worker registry | Supabase table | PostgreSQL table and heartbeat |
| Provider access | Shared `llm_api.py` router | Keep same router; inject route config from secrets |
| Durable files | No authoritative worker-local storage | PostgreSQL metadata + optional S3-compatible object storage |

The worker now depends on the `QueueStore` protocol in `cloud_worker/queue_store.py`. `SupabaseQueueStore` preserves the current PostgREST/RPC behavior. The protocol is the portability boundary, but only the Supabase implementation exists today; this is not yet database-provider independence. Do not configure another backend until its implementation passes the queue contract and recovery tests.

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

1. Run the existing Supabase-backed worker on a free Linux VM. This is the smallest-risk first deployment.
2. [x] Extract current Supabase calls from `worker.py` into a `QueueStore` interface and preserve behavior with a Supabase implementation.
3. [x] Add a PostgreSQL implementation using atomic claim transactions (`FOR UPDATE SKIP LOCKED`), lease renewal, cancellation, progress, terminal-state writes and worker heartbeat. Standalone schema: `postgres/schema.sql`.
4. Add integration tests against a disposable PostgreSQL container, including concurrent claims and expired-lease recovery. The CI integration suite is being added; do not treat the adapter as production-validated until that workflow passes.
5. Containerize the HTTP ingress behind the existing API contract; move off Supabase Edge Functions only after authenticated E2E tests pass.
6. Verify backup/export/restore, then move database and worker together or independently.

## Provider portability acceptance tests

A release is not called portable until:

- The same image starts on amd64 and arm64.
- The same worker contract tests pass against Supabase and standard PostgreSQL adapters.
- A queued task survives worker/container restart.
- Expired leases are recovered without duplicate terminal results.
- SIGTERM does not lose acknowledged task state.
- PostgreSQL export restores into an independent PostgreSQL instance.
- No vendor-specific secret, SDK or URL is required by the Council engine.
