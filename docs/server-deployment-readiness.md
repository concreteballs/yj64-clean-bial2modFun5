# YJ-64 server deployment readiness

Status: server worker exists and is CI-tested; hosting deployment and provider-backed E2E are not yet complete.
Scope: this repository only.

## Architecture found in the repository

This repository already contains a server-side Council runtime:

- `cloud_worker/engine.py`: server-native Council engine. It reuses the shared `llm_api.py` provider router and injects provider credentials at runtime.
- `cloud_worker/worker.py`: persistent queue consumer with bounded concurrency, worker heartbeats, leases, cancellation checks, progress events and terminal result persistence.
- `cloud_worker/Dockerfile`: Python 3.11 slim container.
- `supabase/functions/council-api`: HTTP ingress/control plane.
- `supabase/migrations`: PostgreSQL request queue, claim RPC and worker registry.
- `.github/workflows/council-worker-tests.yml`: compile, deterministic tests and Docker image build.

The Android Base and Monitor APKs are not server deployment artifacts. The Android IPC test remains a legacy client/diagnostic regression test only.

## Current coupling that must be isolated before moving off Supabase

The worker currently calls Supabase-specific APIs directly:

- `supabase.create_client()`
- PostgREST table operations
- RPC `yj64_claim_council_api_request`
- Supabase worker registry tables

The Council engine itself is comparatively portable. The worker's queue/storage adapter and the current Edge Function ingress are the provider-specific boundary. A future self-hosted or non-Supabase deployment must replace those adapters, not the Council engine or public protocol.

## Free hosting assessment (checked 2026-11-19)

### Primary candidate: Oracle Cloud Always Free VM

Official Always Free documentation currently lists:
- Ampere A1 allowance of 1,500 OCPU-hours and 9,000 GB-hours monthly, equivalent for Always Free accounts to 2 OCPUs and 12 GB RAM.
- 200 GB total Always Free block-volume storage.
- 10 TB monthly outbound transfer.
- Resources must be created in the tenancy home region.
- Capacity may be unavailable at provisioning time.
- Idle Always Free compute can be reclaimed when CPU, network and (for A1) memory utilization remain below Oracle's thresholds for seven days.

This is the best fit for a continuously running Docker worker if the user's account can provision the VM. A1 is ARM64, so build and test multi-architecture images (linux/arm64 and linux/amd64) and avoid x86-only native dependencies.

Official docs:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm

### Secondary candidate: Google Cloud Compute Engine Free Tier

Official documentation lists one non-preemptible e2-micro per month in the supported US regions (Oregon, Iowa, South Carolina), 30 GB-month standard persistent disk and 1 GB/month outbound transfer from North America. A billing account is required and usage beyond Free Tier limits is billable. This is a small fallback/test host, not the preferred YJ64 worker host; the supported regions and very low egress allowance are important constraints.

Official docs:
- https://docs.cloud.google.com/free/docs/free-cloud-features

### Not a permanent free worker host

- Render Free Web Services sleep after 15 minutes of inactivity, have no persistent disk and do not offer free Background Worker instances. Render Background Workers are appropriate only on a paid plan.
- Koyeb/Railway and similar free app tiers have compute, storage, credit or sleep limits; treat them as demos/temporary environments, not guaranteed always-on infrastructure.
- Supabase Free is currently the control-plane/database dependency, not a place to run the persistent Python worker. Keep the worker external.
- Neon/Supabase free Postgres may be useful for development, but do not make a sleeping/limited free database the only durable copy. Keep regular PostgreSQL dumps and test restores.

Official Render docs:
- https://render.com/docs/free
- https://render.com/docs/background-workers

## Portability rules (required for all new server work)

1. Keep Council orchestration and provider routing independent from hosting vendor APIs.
2. Use standard Linux containers, Python 3.11+, HTTP/JSON, environment configuration and PostgreSQL semantics.
3. Put queue/database operations behind a small storage adapter. Keep the existing Supabase adapter first; add a standard PostgreSQL adapter before claiming Supabase independence.
4. Keep migrations as ordinary SQL wherever possible. Isolate vendor-specific auth and Edge Function behavior behind the ingress adapter.
5. Persist authoritative task state in PostgreSQL, not container filesystems or ephemeral key-value stores.
6. Treat local files as disposable cache only. Store durable artifacts in PostgreSQL or an S3-compatible object-storage adapter.
7. Keep secrets outside Git, images, APKs and logs. Support environment variables or mounted secret files.
8. Build multi-architecture OCI images (linux/amd64 and linux/arm64); pin base images/dependencies and run the same tests on both architectures.
9. Provide graceful SIGTERM handling, bounded shutdown, restart policy, lease recovery, idempotency and health/readiness checks.
10. Make provider migration a configuration change wherever possible: the same image must run on free VM, paid VPS, dedicated Linux host or user's own hardware.

## Deployment shape

- `api`: HTTP ingress/control plane. Initially the existing Supabase Edge Function; later replaceable by a containerized FastAPI service implementing the same public contract.
- `worker`: current Python Council worker container.
- `database`: PostgreSQL. Initially Supabase-hosted PostgreSQL; later any compatible managed or self-hosted PostgreSQL.
- `object storage`: optional S3-compatible adapter for large artifacts; not required for the current queue payloads.
- `reverse proxy/TLS`: provider-neutral Caddy or equivalent when the API is self-hosted.

The initial Oracle VM deployment can run the worker container while the existing Supabase API/database remain in place. This avoids a risky simultaneous migration. The subsequent portability milestone is replacing Supabase-specific queue calls with a PostgreSQL adapter and adding a self-hosted API container.

## Current deployment blockers

- No external worker host has been provisioned.
- Real provider routes and secrets are not yet installed in a host secret manager.
- No authenticated live provider E2E has been run.
- The worker still uses Supabase-specific PostgREST/RPC calls; a self-hosted PostgreSQL deployment is not yet plug-compatible.
- The worker CI proves deterministic adapter behavior and container build, not cloud deployment, provider credentials, billing, uptime or database portability.

## Safe activation sequence

1. Preserve the existing submit gate as closed.
2. Build and test multi-architecture container artifacts.
3. Provision an eligible free VM and configure firewall/SSH/updates.
4. Install worker secrets in the VM's protected environment file or secret manager.
5. Start one worker container with restart policy; confirm heartbeat and logs.
6. Run controlled authenticated provider E2E, cancellation, lease recovery and terminal persistence tests.
7. Only then enable the API submit gate.
8. Before changing host or database provider, export PostgreSQL data and verify restore in the target environment.

Never commit API keys, database passwords, service-role keys, deployment tokens or real provider credentials.
