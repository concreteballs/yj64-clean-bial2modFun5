# Server CI validation checklist

This checklist defines what the repository's `Council worker tests` workflow must prove before any server deployment is considered ready.

## Automated checks

- Python 3.11 compiles the server API, worker, engine, queue adapters and tests.
- PostgreSQL 16 initializes the owner/runtime roles, schema and least-privilege grants.
- Council engine contract and lifecycle tests pass.
- Supabase queue adapter tests pass.
- PostgreSQL queue tests pass, including atomic claims, lease recovery, cancellation and concurrent workers.
- HTTP API validation and PostgreSQL-backed request lifecycle tests pass.
- Docker Compose configuration validates with the example environment.
- OCI images build for both `linux/amd64` and `linux/arm64`.

## What a green CI run does not prove

CI does not prove that real OpenAI/Gemini credentials work, that a cloud VM has been provisioned, or that public HTTPS, firewall rules, backup restoration and uptime are configured. Those require a separate controlled deployment test.

## Production gate

Keep these values unchanged until the separate deployment acceptance test is complete:

```dotenv
YJ64_COUNCIL_ENGINE_ADAPTER=not_ready
YJ64_COUNCIL_WORKER_ENABLED=false
```

Never put provider keys, agent bearer tokens, database passwords or private endpoint credentials in the repository or CI logs.
