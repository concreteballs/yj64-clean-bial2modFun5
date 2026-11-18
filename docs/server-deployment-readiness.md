# YJ-64 server deployment readiness

Status: architecture assessment for moving runtime work to a free cloud server.
Scope: this repository only. No Android production code is changed by this document.

## Executive decision

Do not deploy the existing Android Base APK or standalone Android Monitor APK as Linux server processes. They are Android applications and depend on Android framework APIs. Build a separate server-native runtime and preserve the diagnostic event contract where practical.

The current Android build remains useful as a protocol/lifecycle reference and as an emulator test target. It is not the server deployment artifact.

## What is Android-specific today

### Embedded internal agent

File: `services/internal_monitor.py`

The current implementation imports and uses:

- `jnius.autoclass`
- `org.kivy.android.PythonService`
- Android `ContentResolver.call()`
- Android `Uri` and `Bundle`
- Android app-private `getFilesDir()`

Its foreground/sticky service lifecycle is configured in `buildozer.spec`. These APIs do not exist in a normal Linux container or VM. The agent cannot be launched unchanged under Docker, Render, or a Linux VM.

### External Monitor

File: `monitor-app/app/src/main/java/org/blackmirror/yj64monitor/DiagnosticReportProvider.java`

This is an Android `ContentProvider`. It authenticates the calling Android package using Binder UID/package information and persists JSONL reports in the Monitor app's private files directory. A Linux service cannot host this component or use Binder identity.

### Existing contract worth preserving

- Schema: `yj64.diagnostic.v1`
- Events currently emitted at startup: `self_diagnostic`, `internal_startup`, `internal_service_ready`
- Event envelope: `schema`, `agent`, `event`, `timestamp_ms`, `report_id`, `data`
- Delivery acknowledgement includes `ok` and the same `report_id`
- Reports are intended to be idempotent and retried if delivery fails.

The Android Content Provider transport should be replaced on the server by authenticated HTTPS endpoints. Keep the schema and acknowledgement semantics stable so the Android implementation can remain a compatible client if needed.

## Proposed server-side split

1. **YJ-64 API / control plane** — HTTP API for health, task submission, status, and diagnostic ingestion.
2. **YJ-64 worker** — long-running process for task execution and internal orchestration. It must be independently restartable.
3. **Persistent storage** — PostgreSQL for task state, report metadata, idempotency keys, and durable status. Do not rely on a container's local filesystem for authoritative state.
4. **Logs and diagnostics** — structured stdout logs plus persisted diagnostic events; expose a health endpoint separately from readiness.
5. **Secrets** — provider/API keys supplied only as server environment secrets, never committed to Git or embedded in APKs.

The existing Android Monitor's report validation rules are a useful starting point, but server authentication must use a server credential (for example, a scoped bearer token), not Android package identity.

## Free hosting assessment (checked 2026-11-19)

- **Oracle Cloud Always Free VM**: best initial candidate for a continuously running Linux worker and Docker Compose deployment. Always Free includes eligible Ampere A1 compute capacity (up to 2 OCPUs / 12 GB RAM equivalent under the published monthly allowance). Availability depends on home region capacity; Oracle also documents possible reclamation of idle instances. Confirm account/region availability before relying on it.
- **Render Free Web Service**: suitable for a small HTTP demo only. It sleeps after 15 minutes without inbound traffic, has an ephemeral filesystem, and cannot run a dedicated background worker on the free compute tier. Do not use it as the only host for a continuously running YJ-64 worker.
- **Supabase Free**: suitable as managed Postgres/auth/storage support, not as the always-on worker host. Edge Functions have a finite execution window and CPU limits; they are request/task handlers, not a permanent daemon.

Official references:
- Oracle Free Tier: https://www.oracle.com/cloud/free/
- Oracle Always Free compute details: https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- Render free services and limitations: https://render.com/docs/free
- Supabase Edge Function limits: https://supabase.com/docs/guides/functions/limits

## Migration sequence

1. Keep the current Android IPC emulator test green as a regression check; it proves the legacy Android transport still works, not server readiness.
2. Define the server HTTP contract for report ingestion, health/readiness, task submission, and task status.
3. Implement a Linux-native diagnostic/worker runtime with no Kivy, PyJNIus, Android SDK, Binder, or Content Provider imports.
4. Add persistent PostgreSQL storage and idempotent report ingestion.
5. Add Dockerfile and deployment configuration for a Linux VM; configure restart policy, health checks, environment secrets, and backups.
6. Deploy to a free VM and run end-to-end tests against the real API/worker.
7. Only after server E2E passes, connect the app/client to the deployed API.

## Current blockers before deployment

- No server-native API/worker entry point exists in this repository yet.
- No server authentication contract or secrets are configured here.
- No authoritative persistent database schema/connection is configured for this runtime.
- No deployment target/account/region has been selected or provisioned.
- The Android APK build and Base-to-Monitor IPC test do not validate any of the above.

## Non-goals for this migration

- Do not attempt to run Android APKs on the Linux host.
- Do not port Android Binder/Content Provider code to the server.
- Do not expose diagnostic ingestion publicly without authentication, size limits, schema validation, and idempotency.
- Do not commit API keys, database passwords, or deployment tokens.
