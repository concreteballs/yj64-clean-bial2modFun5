# YJ-64 Cloud Council Worker

This is a separate, long-running container. It is intentionally not deployed as a Supabase Edge Function: Edge Functions have a finite wall-clock lifetime and are intended for short-lived request handling. The API remains the Edge Function; this worker claims durable requests from PostgreSQL and invokes the existing central YJ-64 provider router.

## Runtime environment

Required variables (set in the worker host's secret manager, never commit them):

- `SUPABASE_URL`: project URL.
- `SUPABASE_SERVICE_ROLE_KEY`: server-only Supabase service-role key.
- `YJ64_COUNCIL_PROVIDER_CONFIG`: JSON object containing at least two configured participant routes.

Example shape with deliberately fake credentials:

```json
{
  "route_1": {
    "provider": "openai",
    "model": "YOUR_MODEL",
    "api_key": "REPLACE_WITH_SECRET",
    "endpoint": "https://api.openai.com/v1"
  },
  "route_2": {
    "provider": "gemini",
    "model": "YOUR_MODEL",
    "api_key": "REPLACE_WITH_SECRET",
    "endpoint": "https://generativelanguage.googleapis.com/v1beta"
  }
}
```

Supported provider names and request formats are inherited from `llm_api.py`. Never put provider credentials in the Android APK, repository, Gateway, or public app configuration.

Optional variables:

- `YJ64_WORKER_ID`: stable unique worker name; otherwise generated.
- `YJ64_WORKER_POLL_SECONDS`: queue polling interval (default 3).
- `YJ64_WORKER_LEASE_SECONDS`: lease duration (default 180, bounded 60–900).
- `YJ64_WORKER_CONCURRENCY`: simultaneous Council requests per container (default 2, bounded 1–8).

## Build and run

```sh
docker build -f cloud_worker/Dockerfile -t yj64-council-worker .
docker run --rm \
  -e SUPABASE_URL \
  -e SUPABASE_SERVICE_ROLE_KEY \
  -e YJ64_COUNCIL_PROVIDER_CONFIG \
  yj64-council-worker
```

The container must run continuously with automatic restart on failure. Use at least two independently configured model routes. Each container handles up to YJ64_WORKER_CONCURRENCY separate requests concurrently; each request gets its own engine instance and progress callback. Scale Render Background Worker instances horizontally to increase capacity further. Total possible concurrent requests = instance count × per-instance concurrency. Provider quotas, latency and cost limits must be reviewed before production traffic is enabled.

## Readiness and activation

The worker publishes a heartbeat to `yj64_council_api_workers`. The API considers the worker live only when a `running` heartbeat is newer than 120 seconds.

Do not set the Edge Function secrets `YJ64_COUNCIL_WORKER_ENABLED=true` and `YJ64_COUNCIL_ENGINE_ADAPTER=ready` until:
1. the worker container is deployed and its heartbeat is visible;
2. provider route secrets are installed in the worker host;
3. a controlled live test has completed using the real providers;
4. cancellation, lease recovery and terminal result persistence have been verified.

The API's submit gate checks both server-side flags and the live worker registry. Until all checks pass, submissions remain closed with HTTP 503.

## Current limitations

- The engine implements independent positions, bounded critique rounds and final structured positions. It does not claim that model agreement is external factual verification.
- Weighted voting is not implemented; when requested, the result explicitly reports weighted voting as disabled and records a limitation.
- The worker uses the central provider router and does not yet implement provider-specific structured-output modes. Invalid final JSON fails the attempt and is retried according to the durable lease policy.
- The container is prepared and CI-tested; no external worker host has yet been selected or deployed.
