# YJ-64 Base

Stage 2 of the YJ-64 staged architecture.

This repository combines:

- a minimal YJ-64 base application;
- the embedded Internal Diagnostic Agent;
- the development Diagnostic Bridge protocol used by the external YJ-64 monitor.

Startup contract:

1. The base activity starts the internal diagnostic service.
2. The internal service runs self-diagnostics.
3. It sends a `yj64.diagnostic.v1` report to the external monitor when the bridge is available.
4. If the bridge is unavailable, the report is persisted locally as JSONL.
5. The internal service records its own startup report.
6. The service hands control back to the base application.
7. A target-launch report records the result.

The package is intentionally `org.blackmirror.blackmirror`, matching the current external YJ-64 monitor target.

The application is deliberately minimal at this stage. The purpose of Stage 2 is to validate the complete lifecycle before the full YJ-64 architecture is introduced.

## Current diagnostic transport

The current embedded diagnostic agent uses Android Content Provider IPC to
communicate with the external monitor:

- authority: `org.blackmirror.yj64monitor.diagnostics`
- method: `receive_report`
- report schema: `yj64.diagnostic.v1`
- configuration: `config/bridge.json`

If the provider is unavailable or does not acknowledge a report, the agent
persists the report in the app-private JSONL spool and retries forwarding it
later. The current implementation does not use the loopback TCP endpoint
`127.0.0.1:9333`; that description was stale.

An optional HTTPS upload function exists in the diagnostic agent, but
`report.https_endpoint` is empty by default. No cloud reporting endpoint is
configured by this repository yet. The separate, user-initiated GitHub report
upload in the monitor UI is not the diagnostic IPC transport.


Stage 2 build trigger: embedded-agent base integration.

## Server deployment

This repository currently builds an Android client and Android diagnostic Monitor. These APKs are not the server deployment target. The Linux server migration assessment, Android-specific dependencies, proposed server split, free-hosting assessment, and migration sequence are documented in [docs/server-deployment-readiness.md](docs/server-deployment-readiness.md).
