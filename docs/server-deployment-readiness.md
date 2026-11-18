# YJ-64 server deployment readiness

Status: portable API, PostgreSQL queue adapter and worker containers are implemented. Automated CI and live authenticated provider verification remain outstanding.
Scope: `concreteballs/yj64-clean-bial2modFun5` only.

## Server architecture now present

- `cloud_worker/engine.py`: server-side Council engine using the shared `llm_api.py` provider router.
- `cloud_worker/worker.py`: persistent worker with bounded concurrency, heartbeat, lease renewal, cancellation, progress and terminal persistence.
- `cloud_worker/queue_store.py`: `SupabaseQueueStore` compatibility adapter and standard `PostgresQueueStore`.
- `cloud_worker/api.py`: FastAPI ingress implementing the existing `yj64.council-api.v1` contract (submit, idempotency, status, result and cancellation).
- `cloud_worker/postgres/schema.sql`: standalone PostgreSQL schema for agents, requests, events and worker registry.
- `cloud_worker/compose.yaml`: API and worker run from the same OCI image and share one `DATABASE_URL`.
- `.github/workflows/council-worker-tests.yml`: deterministic tests, disposable PostgreSQL 16 integration tests and multi-architecture OCI build.

The Android Base and Monitor APKs are not server deployment artifacts.

## Migration and compatibility

The previous Supabase Edge Function and Supabase queue adapter remain available as a separate fallback. Do not mix deployment modes: a Supabase Edge Function must use the Supabase worker adapter; the standalone FastAPI ingress must use the PostgreSQL worker adapter. API and worker always share the same database.

The Council engine and provider router remain independent of the hosting vendor. The standalone API uses standard PostgreSQL and does not require Supabase SDKs, Edge Functions, RLS or PostgREST.

## Hosting choice (reviewed 2026-11-19)

### Primary: Oracle Cloud Always Free VM

Oracle's official Always Free documentation lists the Ampere A1 allowance equivalent to 2 OCPUs and 12 GB RAM for qualifying tenancies, plus 200 GB block storage. A1 is ARM64, so the server image must support `linux/arm64`. Regional capacity is not guaranteed and Oracle may reclaim idle Always Free compute. Confirm current eligibility and limits during provisioning.

Official docs:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm

### Secondary: Google Cloud e2-micro Free Tier

One non-preemptible e2-micro is free only in selected US regions, with 30 GB-month standard persistent disk and a very small 1 GB/month outbound transfer allowance. A billing account is required; overages can be charged. Suitable only as a small fallback/test host.

Official docs:
- https://docs.cloud.google.com/free/docs/free-cloud-features

### Not suitable for a permanent free worker

Render Free Web Services sleep after inactivity, use ephemeral filesystems and do not include free Background Worker instances. Other free app/database tiers may impose sleep, compute, storage or credit limits. They are not a substitute for a durable always-on queue host.

Official docs:
- https://render.com/docs/free
- https://render.com/docs/background-workers

## Portability requirements

1. Council orchestration stays independent from hosting vendor APIs.
2. Use standard OCI containers, Python 3.11+, HTTP/JSON and PostgreSQL.
3. Keep database access behind the `QueueStore` protocol.
4. Store authoritative task state in PostgreSQL, never the container filesystem.
5. Inject provider and database secrets at runtime; never commit secrets or bake them into images.
6. Build and test `linux/amd64` and `linux/arm64`.
7. Preserve idempotency, cancellation, bounded execution, lease recovery and graceful shutdown.
8. Reuse the same image on free VM, paid VPS, dedicated host or user-owned Linux hardware.

## Current remaining blockers

- GitHub Actions must complete successfully for the latest API/worker changes. The connector currently does not expose the push workflow run status reliably, so do not mark CI as passed until the run is visible in GitHub Actions.
- No external host or standalone PostgreSQL instance has been provisioned.
- Real provider credentials are not installed and no authenticated live provider execution has been performed.
- The agent-token provisioning and HTTPS reverse proxy must be configured on the target host.
- PostgreSQL backup/restore must be tested before relying on the deployment.

## Safe activation order

1. Keep `YJ64_COUNCIL_ENGINE_ADAPTER=not_ready` and `YJ64_COUNCIL_WORKER_ENABLED=false`.
2. Verify GitHub Actions tests and multi-architecture image build.
3. Provision the free Linux VM and PostgreSQL database.
4. Apply `cloud_worker/postgres/schema.sql`, create runtime credentials and configure the HTTPS reverse proxy.
5. Install provider secrets and agent token hashes securely.
6. Verify worker heartbeat and API health.
7. Run authenticated submit → execution → status → result, idempotency, cancellation and lease-recovery tests.
8. Only after all checks pass, explicitly open the submit gate.
9. Test PostgreSQL backup and restore before moving to a paid or self-hosted server.

Never place API keys, database passwords, bearer tokens, service-role keys or deployment credentials in Git, APKs, logs or chat.
