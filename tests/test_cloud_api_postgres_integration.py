"""End-to-end HTTP contract tests against disposable PostgreSQL."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid

import psycopg
from fastapi.testclient import TestClient

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
API_DATABASE_URL = os.environ.get("RUNTIME_DATABASE_URL", TEST_DATABASE_URL)
if API_DATABASE_URL:
    os.environ["DATABASE_URL"] = API_DATABASE_URL

from cloud_worker import api  # noqa: E402
from cloud_worker.queue_store import PostgresQueueStore  # noqa: E402
from cloud_worker import worker as council_worker  # noqa: E402


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL is not configured")
class PortableCouncilApiPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = Path("cloud_worker/postgres/schema.sql").read_text(encoding="utf-8")
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            conn.execute(schema, prepare=False)
        cls.client = TestClient(api.app)
        cls.token = "integration-test-token-value-0123456789"
        cls.agent_id = "api-integration-agent"
        cls.token_hash = hashlib.sha256(cls.token.encode()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            conn.execute(
                "TRUNCATE public.yj64_council_api_events, "
                "public.yj64_council_api_requests, "
                "public.yj64_council_api_workers, "
                "public.yj64_council_api_agents CASCADE"
            )
        if api._pool is not None:
            api._pool.close()
            api._pool = None

    def setUp(self):
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            conn.execute(
                "TRUNCATE public.yj64_council_api_events, "
                "public.yj64_council_api_requests, "
                "public.yj64_council_api_workers, "
                "public.yj64_council_api_agents CASCADE"
            )
            conn.execute(
                "INSERT INTO public.yj64_council_api_agents(agent_id, token_hash) VALUES (%s, %s)",
                (self.agent_id, self.token_hash),
            )
            conn.execute(
                "INSERT INTO public.yj64_council_api_workers(worker_id, status, version, routes) "
                "VALUES ('test-worker', 'running', 'test', ARRAY['route_1','route_2'])"
            )
        os.environ["YJ64_COUNCIL_ENGINE_ADAPTER"] = "ready"
        os.environ["YJ64_COUNCIL_WORKER_ENABLED"] = "true"

    def tearDown(self):
        os.environ.pop("YJ64_COUNCIL_ENGINE_ADAPTER", None)
        os.environ.pop("YJ64_COUNCIL_WORKER_ENABLED", None)

    def headers(self, idem=None):
        values = {
            "Authorization": f"Bearer {self.token}",
            "x-yj64-protocol-version": api.VERSION,
        }
        if idem:
            values["Idempotency-Key"] = idem
        return values

    def body(self, idem):
        return {
            "protocol_version": api.VERSION,
            "agent_id": self.agent_id,
            "correlation_id": "corr-" + uuid.uuid4().hex[:12],
            "idempotency_key": idem,
            "mode": "consensus",
            "task": {
                "title": "Integration test",
                "prompt": "Do not call any model; this request is cancelled before worker pickup.",
                "context": {},
                "evidence_refs": [],
            },
            "limits": {
                "max_rounds": 1,
                "timeout_seconds": 60,
                "max_output_tokens": 256,
                "minimum_critique_rounds": 1,
                "allow_early_stop": False,
            },
            "voting": {"enabled": False, "weighted": False},
        }

    def test_submit_idempotency_status_and_cancel_contract(self):
        idem = "idem-" + uuid.uuid4().hex
        submitted = self.client.post(
            api.REQUEST_PATH, json=self.body(idem), headers=self.headers(idem)
        )
        self.assertEqual(submitted.status_code, 202, submitted.text)
        first = submitted.json()
        self.assertEqual(first["status"], "accepted")

        replay = self.client.post(
            api.REQUEST_PATH, json=self.body(idem), headers=self.headers(idem)
        )
        # A different correlation ID changes the canonical request hash.
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(replay.json()["error"], "idempotency_conflict")

        # An exact retry reuses the original request identity.
        exact = self.body("idem-exact-" + uuid.uuid4().hex)
        exact["correlation_id"] = "corr-fixed-123456"
        exact_idem = exact["idempotency_key"]
        first_exact = self.client.post(
            api.REQUEST_PATH, json=exact, headers=self.headers(exact_idem)
        )
        retry_exact = self.client.post(
            api.REQUEST_PATH, json=exact, headers=self.headers(exact_idem)
        )
        self.assertEqual(first_exact.status_code, 202)
        self.assertEqual(retry_exact.status_code, 202)
        self.assertEqual(first_exact.json()["request_id"], retry_exact.json()["request_id"])

        request_id = first_exact.json()["request_id"]
        status = self.client.get(
            f"{api.REQUEST_PATH}/{request_id}", headers=self.headers()
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "accepted")

        cancelled = self.client.post(
            f"{api.REQUEST_PATH}/{request_id}/cancel",
            json={"protocol_version": api.VERSION, "agent_id": self.agent_id},
            headers=self.headers(),
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.json()["status"], "cancelled")

        result = self.client.get(
            f"{api.REQUEST_PATH}/{request_id}/result", headers=self.headers()
        )
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.json()["error"], "cancelled")


    def test_submit_worker_execution_and_result_round_trip(self):
        idem = "idem-worker-" + uuid.uuid4().hex
        submitted = self.client.post(
            api.REQUEST_PATH, json=self.body(idem), headers=self.headers(idem)
        )
        self.assertEqual(submitted.status_code, 202, submitted.text)
        request_id = submitted.json()["request_id"]

        class DeterministicTestEngine:
            def __init__(self, routes, report):
                self.report = report

            def run(self, request, claimed_request_id, session_id, is_cancelled):
                self.report({"phase": "mock_provider_execution", "provider_calls": 0})
                self.assert_not_cancelled = not is_cancelled()
                if not self.assert_not_cancelled:
                    raise RuntimeError("Unexpected cancellation in integration test")
                return {
                    "protocol_version": api.VERSION,
                    "request_id": claimed_request_id,
                    "session_id": session_id,
                    "status": "completed",
                    "outcome": "qualified_consensus",
                    "summary": "Deterministic worker integration result; no external provider was called.",
                    "claims": [],
                    "participant_positions": [
                        {"participant_id": "route_1", "position": "Test position", "rationale": "Mocked"}
                    ],
                    "dissent": [],
                    "evidence": [],
                    "unresolved_questions": [],
                }

        with PostgresQueueStore(TEST_DATABASE_URL, max_size=4) as_unused:
            pass

        store = PostgresQueueStore(TEST_DATABASE_URL, max_size=4)
        try:
            row = store.claim("integration-worker", 90)
            self.assertIsNotNone(row)
            self.assertEqual(row["request_id"], request_id)
            with patch.object(council_worker, "CouncilEngine", DeterministicTestEngine):
                council_worker.process(
                    store, row,
                    {
                        "route_1": {"provider": "mock", "model": "test", "api_key": "not-used"},
                        "route_2": {"provider": "mock", "model": "test", "api_key": "not-used"},
                    },
                )
        finally:
            store.close()

        status = self.client.get(
            f"{api.REQUEST_PATH}/{request_id}", headers=self.headers()
        )
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()["status"], "completed")
        result = self.client.get(
            f"{api.REQUEST_PATH}/{request_id}/result", headers=self.headers()
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["outcome"], "qualified_consensus")
        self.assertIn("Deterministic worker integration result", result.json()["summary"])

    def test_submit_gate_remains_closed_without_explicit_enablement(self):
        os.environ["YJ64_COUNCIL_WORKER_ENABLED"] = "false"
        idem = "idem-gate-" + uuid.uuid4().hex
        response = self.client.post(
            api.REQUEST_PATH,
            json=self.body(idem),
            headers=self.headers(idem),
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "council_engine_not_ready")


if __name__ == "__main__":
    unittest.main()
