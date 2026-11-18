# YJ-64 Council Worker — deployment

The Council API ingress is a Supabase Edge Function. The Python Council worker is a **separate persistent container**; do not run it inside the Edge Function or Android APK.

## Container

Build from the repository root:

```sh
docker build -f cloud_worker/Dockerfile -t yj64-council-worker:latest .
docker run --rm --env-file .env yj64-council-worker:latest
```

The image starts `python -m cloud_worker.worker`.

## Required runtime secrets

Configure these directly in the chosen container host's secret manager. Do not commit them to GitHub, put them in the APK, or paste provider keys into issue logs.

- `SUPABASE_URL`: `https://ggambesixwejgbjwtnhw.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service-role secret for this project
- `YJ64_COUNCIL_PROVIDER_CONFIG`: JSON object with at least two configured routes.

Example shape only — replace every placeholder with real provider values in the host's secret manager:

```json
{
  "route_1": {
    "provider": "openai",
    "model": "YOUR_MODEL_ID",
    "api_key": "INJECT_SECRET",
    "endpoint": ""
  },
  "route_2": {
    "provider": "gemini",
    "model": "YOUR_MODEL_ID",
    "api_key": "INJECT_SECRET",
    "endpoint": ""
  }
}
```

Supported provider IDs and endpoint behavior are inherited from `llm_api.py`. Provider credentials are injected in memory through `config_override`; the worker does not read the Android app's local configuration.

Optional settings:
- `YJ64_WORKER_POLL_SECONDS` (default 3)
- `YJ64_WORKER_LEASE_SECONDS` (default 180; allowed 60–900)
- `YJ64_WORKER_ID` (generated uniquely per instance if omitted)
- `YJ64_WORKER_CONCURRENCY` (default 2 simultaneous requests per instance; bounded 1–8)

## Activation sequence

1. In Render, create a Background Worker service from this repository. Set Runtime = Docker, Dockerfile Path = cloud_worker/Dockerfile, Docker Context = repository root, and enable automatic deploy/restart. Do not create a Web Service for the queue consumer.
2. Start with one instance and YJ64_WORKER_CONCURRENCY=2. After live load tests, increase the Background Worker instance count; each replica claims different queue rows atomically. Capacity is instance count × per-instance concurrency.
3. Add the three required secrets above. Start with two provider routes; no production key is needed for CI.
4. Confirm worker logs show `YJ-64 Council worker ... ready` and the Supabase table `yj64_council_api_workers` receives a heartbeat every poll cycle.
5. Check the API `/health` response. It must show `worker: running`.
6. Only after confirming the real provider routes and end-to-end request lifecycle, set Supabase Edge Function secrets:
   - `YJ64_COUNCIL_ENGINE_ADAPTER=ready`
   - `YJ64_COUNCIL_WORKER_ENABLED=true`
7. Run the dedicated authenticated end-to-end test with a newly provisioned machine identity and token. Never use a provider key as the machine token.

Until steps 1–6 are completed, keep request intake disabled. The worker is not deployed merely because the Docker image builds.

## What CI proves

The `Council Worker CI` workflow compiles the router/worker, runs deterministic adapter tests with mocked model responses, and builds the Docker image. It does not call paid model APIs, provision secrets, or deploy a persistent worker.
