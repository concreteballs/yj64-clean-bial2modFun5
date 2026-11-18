# YJ-64 Council API Implementation Audit

**Repository:** concreteballs/yj64-clean-bial2modFun5  
**Branch:** main  
**Protocol target:** yj64.council-api.v1  
**Status:** Audit completed; cloud API implementation not yet present.

## 1. Existing mechanisms

- `llm_api.py`: central provider router, route configuration, provider-specific requests, and response parsing. Credentials are stored in app-private router configuration.
- `message_distributor.py`: maps participants to route IDs and dispatches real model requests through `llm_api.generate_response`.
- `main.py`: common chat, critique mode, and group dialogue UI.
- `chat_workspace.py`: persistent local chats, message history, agents, and named participant histories.
- Group dialogue is implemented in `YJ64BaseApp._open_group_dialogue` (main.py). It requires at least two configured participants, cycles participants for a user-selected 1–20 rounds, and dispatches real requests. It logs events locally.
- Critique currently modifies prompt instructions in `_practical_instructions`; it is not a distinct structured critique session protocol.
- Group dialogue is a sequential round loop; it does not independently validate evidence, extract structured claims, evaluate agreement, or produce a typed consensus outcome.
- Local chat/history persistence does not provide durable cloud request ownership, idempotency, or recovery for an external agent's request.

## 2. Reuse and boundaries

The API must reuse the participant routes and provider router; it must not add a second LLM router. It must invoke a dedicated bounded Council session protocol, building on existing discussion/critique mechanisms while adding independent position, critique, response/reconciliation, and structured outcome stages.

The current Android/Kivy app is not a continuously hosted network service. The external API must run in a cloud/server runtime with durable storage and queue/worker support. The Android app remains a client and must not be treated as the API server.

No cloud Council API server, durable request queue, external-agent machine authentication, or public API route implementation was found in the audited app repository.

## 3. API operations (proposed v1 logical contract)

The Engineering Core Gateway integration document already specifies these routes; use them as the shared contract:

- `POST /api/v1/external-agents/council/requests` — submit task; require authenticated agent, idempotency key, mode and task.
- `GET /api/v1/external-agents/council/requests/{request_id}` — execution status and progress.
- `GET /api/v1/external-agents/council/requests/{request_id}/result` — structured result, available only when ready.
- `POST /api/v1/external-agents/council/requests/{request_id}/cancel` — owner-authorized cancellation.

The API is asynchronous. Submit returns `accepted` and request/session IDs; polling does not create or restart a Council session.

## 4. Execution status and substantive outcome

Execution statuses:
`accepted`, `running`, `completed`, `blocked`, `failed`, `cancelled`.

Substantive outcomes (only for completed analysis):
`consensus`, `qualified_consensus`, `unresolved_disagreement`, `insufficient_evidence`.

Execution status and outcome are separate fields. A timeout, failure, cancellation, block, or missing evidence cannot be mapped to positive consensus.

## 5. Minimum structured result

The v1 result must carry request/session IDs, protocol version, mode, status and outcome, summary, typed claims (Fact/Inference/Hypothesis/Test Result), participant positions, significant disagreement/minority position, evidence references, unresolved questions, assumptions, limitations, rounds and termination reason, and actual tests/simulations performed. Voting is optional, disabled by default, and only aggregate vote results may be exposed.

## 6. Security and persistence requirements

- Separate machine identity for each external agent, least-privilege scopes, owner/tenant checks on every read/cancel.
- Idempotency key bound to authenticated agent; repeat submit returns the existing request/session.
- Durable request/session state and worker recovery after restart.
- Bounded payload, response, round, time, and provider-cost limits; rate limiting and audit events.
- Safe logs: no provider credentials, hidden prompts, private ballots, personal model ratings, or full sensitive content by default.
- Voting disabled by default; if enabled, expose aggregate results only.

## 7. Implementation sequence

1. Complete this repository audit (this document).
2. Agree the API contract with Engineering Core/Council Gateway and confirm the cloud runtime location.
3. Implement cloud API/auth, durable request store, worker/recovery and cancellation.
4. Connect the worker to the existing Council protocol (real provider router and participants), implement Consensus/Critique protocol and validated result schema.
5. Add API unit/integration/recovery tests and CI end-to-end verification.
6. Publish OpenAPI/JSON Schema, deployment configuration names, actual route URLs, commit SHA, CI result and limitations.

## 8. Audit sources

- `main.py`: `_open_group_dialogue`, `_practical_instructions`, `_chat_target_details`, and participant request dispatch.
- `message_distributor.py`: participant routing and dispatch.
- `llm_api.py`: central provider API router.
- `chat_workspace.py`: local chat/session history storage.
- `docs/YJ64-CLOUD-DEPLOYMENT-AND-INTEGRATION-PLAN.md`: sections 8.1 and 8.2 for consensus integrity and external API requirements.
