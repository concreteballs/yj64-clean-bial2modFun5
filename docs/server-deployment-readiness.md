# YJ-64 server deployment readiness

Status: portable API, PostgreSQL queue adapter, persistent worker and a no-card GitHub Actions worker mode are implemented. Automated CI and authenticated live provider verification remain separate gates.
Scope: `concreteballs/yj64-clean-bial2modFun5` only.

## Server architecture now present

- `cloud_worker/engine.py`: server-side Council engine using the shared `llm_api.py` provider router.
- `cloud_worker/worker.py`: persistent Council worker with bounded concurrency, heartbeat, lease renewal, cancellation, progress and terminal persistence.
- `cloud_worker/github_actions_runner.py`: bounded-lifetime wrapper for GitHub-hosted runners; it runs the same worker and shuts it down before the hosted-job timeout.
- `cloud_worker/queue_store.py`: Supabase compatibility adapter and standard PostgreSQL adapter.
- `cloud_worker/api.py`: standalone FastAPI ingress implementing the existing `yj64.council-api.v1` contract.
- `cloud_worker/postgres/schema.sql`: standalone PostgreSQL schema.
- `.github/workflows/council-worker-free.yml`: two independent Supabase-backed workers on GitHub-hosted runners, scheduled every five minutes and manually dispatchable.
- `.github/workflows/council-worker-tests.yml`: deterministic tests, disposable PostgreSQL integration tests and multi-architecture OCI build.

The Android Base and Monitor APKs are not server deployment artifacts.

## No-card hosting mode

The public repository uses standard GitHub-hosted runners. GitHub documents standard runners as free and unlimited for public repositories. The workflow runs two independent worker jobs, each with concurrency 1, and keeps their heartbeat alive while the runner is active. The workflow-level concurrency group prevents overlapping worker fleets. Scheduled starts may be delayed by GitHub; this is not a guaranteed always-on service.

The workflow uses the existing Supabase queue adapter and does not deploy or modify the Supabase Edge Function. Required repository Actions secrets:

- `YJ64_SUPABASE_URL`
- `YJ64_SUPABASE_SERVICE_ROLE_KEY`
- `YJ64_COUNCIL_PROVIDER_CONFIG`

The provider config must contain at least two configured routes, following `cloud_worker/.env.example`. Secrets are read only by the workflow and are never written to the repository. Do not print them in logs.

GitHub Actions infrastructure is free for standard runners in public repositories under GitHub's documented policy. Supabase Free quotas still apply. Provider API usage is separate and may be billable according to the provider account; the workflow does not make provider calls unless it claims a real queued task.

## Safety gates

- Keep the deployed `council-api` Edge Function intake gate closed until authenticated live provider tests, independent-session checks and cancellation tests pass.
- The GitHub Actions workflow does not change Supabase function secrets or environment variables.
- Do not add credentials to files, commits, artifacts or logs.
- If Actions secrets are missing, the workflow reports an idle notice and does not start the worker.
- Each worker has its own ID and processes requests through the database's atomic claim function. Request/session IDs remain the source of chat isolation.
- GitHub-hosted jobs have a six-hour maximum execution time. This wrapper requests graceful shutdown after 5 hours 40 minutes; any task interrupted by runner termination must be recovered through its database lease.

## Separate standalone PostgreSQL mode

The repository also retains the portable API and worker containers using standard PostgreSQL. This mode is not deployed by the GitHub Actions workflow. It requires an independently hosted PostgreSQL database and a persistent host, so it is not the selected no-card path.

## Remaining verification

1. Configure the three Actions secrets after checking the provider accounts' billing limits.
2. Confirm the workflow starts two worker heartbeats without claiming any test/fake task.
3. Keep intake disabled until the user explicitly authorizes the live end-to-end test sequence.
4. Verify two real, independently identified requests, result routing, cancellation and lease recovery.
5. Only then consider opening the API intake gate with separate explicit approval.

A passing CI run does not prove provider credentials, live model execution, production uptime or free provider usage.
