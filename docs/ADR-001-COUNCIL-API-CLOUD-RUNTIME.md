# ADR-001: Cloud runtime and durable execution for the external Council API

- **Status:** Partially accepted — Supabase Edge Function API transport deployed; worker runtime and engine adapter remain Proposed.
- **Date:** 2026-11-18
- **Scope:** `concreteballs/yj64-clean-bial2modFun5`, branch `main`.
- **Related contract:** [OpenAPI](./openapi/council-api-v1.yaml), protocol `yj64.council-api.v1`.
- **Boundary:** This ADR does not authorize changes to `concreteballs/YJ64-Engineering-Core`.

## Context

The Engineering Core repository already contains the v1 JSON Schema, an HTTPS Gateway client, durable task/checkpoint handling, and a result consumer. Its documentation explicitly treats the four Council routes as routes that the YJ-64 application must implement.

The Android/Kivy application is a client. Its local JSON chat history, provider router and Android diagnostic Content Provider do not provide a remotely reachable, durable Council service. A phone or Android emulator must never be a dependency for remote Council execution.

The existing cloud plan identifies a Supabase project named `YJ64-Autonomous-Core` and existing PostgreSQL queue/storage infrastructure on the Engineering Core side. Reuse is a possibility, not an assumption: ownership, schema isolation, credentials, RLS and operational responsibilities must be checked before the application API is connected to it.

## Decision proposal

Adopt a **cloud-first split**:

1. **HTTPS API:** a stateless Python service deployed independently of the Android client. Vercel is the first deployment candidate because a Vercel Python service is already used in this ecosystem; this is not proof that the existing deployment is suitable for Council traffic. Before acceptance, verify a reachable production/staging URL, Python runtime/dependency support, request duration/body limits, secret management, logs and health checks.
2. **Durable intake and state:** PostgreSQL stores machine identities/scopes, request ownership, idempotency records, Council session references, lifecycle state, progress, cancellation intent and audit metadata. All reads/writes are server-side and owner-scoped.
3. **Queue and worker:** persist a queue item in the same transaction as request acceptance. Execute Council work in a separate worker process or bounded scheduled worker; do not run long model calls inside the HTTP request. The worker claims jobs with leases, persists checkpoints, observes deadlines/cancellation, and can resume after restart. A scheduled worker is acceptable only if its execution window and cadence meet the agreed latency/timeout limits.
4. **Artifacts:** large/private evidence and result artifacts live in private object storage; API responses expose only authorized references and normalized structured results.
5. **Council adapter:** the worker calls a server-side adapter to the real YJ-64 Council/router/session engine. The adapter must execute actual participants and formal Consensus/Critique lifecycle. It must not return synthetic success or infer consensus from a chat marker.
6. **Secrets:** machine tokens and model-provider credentials exist only in server-side secret storage. Never embed them in APK, browser bundles, Gateway configuration committed to Git, or logs.

### Storage reuse rule

The existing `YJ64-Autonomous-Core` Supabase project may be reused only after verifying:
- the project is available to the application service owner and its production region/plan is suitable;
- separate application-owned schema/tables and least-privilege server credentials can be established;
- RLS and service-role access do not expose Engineering Core or other tenants' data;
- queue ownership, backup/retention, migrations and incident responsibility are explicit.

If any condition fails, provision a separately approved database/queue. Do not create a second project or duplicate tables before this check.

## Alternatives considered

- **Android emulator / phone as API host:** rejected. It is not a stable public service, cannot guarantee availability, and must not be required for Council execution.
- **Synchronous API request that runs the entire Council:** rejected. Long-running model calls, retries and client disconnects require durable asynchronous execution.
- **Vercel function as the only worker/state store:** rejected. Function memory and request lifetime are not durable job state.
- **Reuse the Gateway's own database tables directly:** not assumed. The app API needs explicit ownership, schema and credential boundaries; reuse requires the storage checks above.
- **Mock endpoint returning completed/consensus:** rejected. It would falsely signal that the real Council ran.

## Required API behavior

- Implement the four operations in the OpenAPI document.
- Require HTTPS and a machine Bearer token with scopes; bind every request/session to the authenticated machine identity and enforce ownership on status, result and cancellation.
- Validate the exact `yj64.council-api.v1` payload, size limits and protocol header.
- Enforce idempotency for `agent_id + idempotency_key`; same key and same canonical payload returns the original accepted identifiers, while a different payload returns `409 idempotency_conflict`.
- Return `202 Accepted` only after durable request and queue persistence.
- Distinguish execution status from substantive outcome. `blocked`, `failed`, `cancelled` and `insufficient_evidence` must never be relabelled as consensus.
- A completed result is available only when the real Council lifecycle has completed and the structured result has passed validation.
- Cancellation is owner-scoped and idempotent; report the actual terminal state if completion won the race.
- Apply rate limits, bounded payloads, timeouts, retry policy, audit events and redacted logs.

## Acceptance gates before implementation

1. Verify the Vercel candidate with a harmless health endpoint and deployment smoke test; document the actual service URL and runtime constraints. No production URL is assumed by this ADR.
2. Verify Supabase project ownership/access, region, queue capability, private storage, RLS and server credentials; document whether the existing project is reused or a separate one is approved.
3. Identify the actual server-callable Council/router/session interface in this repository. If the current Kivy application cannot be imported safely in a server process, extract a platform-neutral service layer without changing Android behavior.
4. Define migrations, queue lease/recovery semantics, worker scheduling and cancellation behavior.
5. Add contract tests against the Gateway schema/fixtures and negative tests for auth, scope, ownership, idempotency, invalid payloads and terminal states.
6. Only after these gates, implement the API and worker. Then run live Gateway-to-YJ64 E2E using real provider credentials and verify a durable result artifact.

## Consequences

This design makes the API independently deployable and keeps the Android app as a lightweight client. It introduces cloud operations (database, queue, worker, secrets, monitoring) that must be tested and documented. This ADR is a proposal, not evidence that any endpoint or Council worker is already deployed.


## Deployment findings — 2026-11-18

The existing Supabase project `YJ64-Autonomous-Core` was verified as `ACTIVE_HEALTHY` in `eu-central-1` with PostgreSQL 17.12. It already has a private Storage bucket `yj64-private-artifacts`. Existing Core queue/checkpoint tables are active and contain data, so the application API uses isolated `yj64_council_api_*` tables rather than modifying or claiming the shared Core queue.

The API transport is now deployed as Supabase Edge Function `council-api`, version 5, at:

`https://ggambesixwejgbjwtnhw.supabase.co/functions/v1/council-api`

The function implements the four Gateway operations, custom machine Bearer authentication using stored SHA-256 token hashes, scopes, owner-scoped reads, idempotency, request persistence, cancellation and result-shape checks. The database tables have RLS enabled, no client policies, no `anon`/`authenticated` SELECT grants, and server-role access only. The audit sequence is also restricted to server role.

The submit route is deliberately feature-gated. Until a real worker and server-side Council adapter are deployed, it returns `503 council_engine_not_ready`. The public health response reports the API and database availability but explicitly reports `worker: not_deployed`, `council_engine: not_connected`, and `ready_for_requests: false`. No machine token or provider secret has been provisioned.

The Edge Function is the selected API ingress. A separate long-running worker runtime is still undecided; it must not be assumed to be the same short-lived Edge Function. The existing `yj64-private-artifacts` bucket is private and can be used for result artifacts after access policy and object-key ownership are defined. The `pgmq` and `pg_cron` extensions are available but not installed; no dependency on them is assumed.

The current `llm_api.py` reads provider configuration from the local app `user_data_dir`. It cannot be invoked as a secure cloud Council engine without a platform-neutral adapter and separately provisioned server credentials. Therefore this ADR does not claim full Council execution readiness.


## Smoke-test evidence

GitHub Actions `Council API smoke test` run #8 passed against deployed Edge Function v5. It verified API/database health, mandatory protocol header, rejection of invalid machine credentials, and the submit readiness gate returning `503 council_engine_not_ready`. This confirms the transport/security gate only; it does not prove real Council execution or Gateway end-to-end integration.


## Extended route and database verification

GitHub Actions smoke test run #9 passed. It verifies health, required protocol version, rejection of invalid machine credentials on status/result/cancel, and the fail-closed submit gate. Direct database checks confirm RLS enabled on all three API tables, no SELECT privileges for `anon` or `authenticated`, server-role-only access to the audit sequence and worker claim function, zero registered machine agents and zero request rows. No test task or provider call was executed.

The Gateway must include the public Supabase `apikey` header as well as its own secret machine Bearer token. This is a cross-repository client change and is intentionally not applied to Engineering Core in this repository's work.
