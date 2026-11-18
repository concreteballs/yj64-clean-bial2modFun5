"""Integration tests for the portable PostgreSQL queue adapter.

Set TEST_DATABASE_URL to a disposable PostgreSQL database. CI provides one.
"""
from __future__ import annotations

import os
from pathlib import Path
import threading
import unittest
import uuid

import psycopg
from psycopg.types.json import Jsonb

from cloud_worker.queue_store import PostgresQueueStore


DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "TEST_DATABASE_URL is not configured")
class PostgresQueueStoreIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = PostgresQueueStore(DATABASE_URL, max_size=8)
        schema = Path("cloud_worker/postgres/schema.sql").read_text(encoding="utf-8")
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(schema, prepare=False)

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "TRUNCATE public.yj64_council_api_events, "
                "public.yj64_council_api_requests, "
                "public.yj64_council_api_workers, "
                "public.yj64_council_api_agents CASCADE"
            )
        cls.store.close()

    def setUp(self):
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "TRUNCATE public.yj64_council_api_events, "
                "public.yj64_council_api_requests, "
                "public.yj64_council_api_workers, "
                "public.yj64_council_api_agents CASCADE"
            )
            self.agent_id = "test-agent"
            conn.execute(
                "INSERT INTO public.yj64_council_api_agents(agent_id, token_hash) "
                "VALUES (%s, %s)",
                (self.agent_id, "a" * 64),
            )
        self.request_id = self._insert_request()

    def _insert_request(self):
        request_id = str(uuid.uuid4())
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                """
                INSERT INTO public.yj64_council_api_requests
                    (request_id, agent_id, correlation_id, idempotency_key,
                     request_hash, protocol_version, mode, task, limits, voting)
                VALUES (%s, %s, %s, %s, %s, 'yj64.council-api.v1', 'consensus',
                        %s, %s, %s)
                """,
                (
                    request_id, self.agent_id, "corr-" + request_id[:8],
                    "idem-" + request_id[:12], "b" * 64,
                    Jsonb({"title": "test", "prompt": "test"}),
                    Jsonb({"max_rounds": 1, "timeout_seconds": 60, "max_output_tokens": 256}),
                    Jsonb({"enabled": False, "weighted": False}),
                ),
            )
        return request_id

    def test_claim_is_atomic_and_increments_attempts(self):
        row = self.store.claim("worker-a", 90)
        self.assertEqual(row["request_id"], self.request_id)
        self.assertEqual(row["worker_id"], "worker-a")
        self.assertEqual(row["attempts"], 1)
        self.assertIsNone(self.store.claim("worker-b", 90))

    def test_expired_lease_can_be_recovered_by_another_worker(self):
        first = self.store.claim("worker-a", 90)
        self.assertIsNotNone(first)
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "UPDATE public.yj64_council_api_requests "
                "SET lease_expires_at = now() - interval '1 second' "
                "WHERE request_id = %s",
                (self.request_id,),
            )
        recovered = self.store.claim("worker-b", 90)
        self.assertEqual(recovered["worker_id"], "worker-b")
        self.assertEqual(recovered["attempts"], 2)

    def test_cancellation_progress_terminal_result_and_event(self):
        row = self.store.claim("worker-a", 90)
        self.store.update_progress(self.request_id, "worker-a", {"phase": "critique"})
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "UPDATE public.yj64_council_api_requests SET cancel_requested = true "
                "WHERE request_id = %s",
                (self.request_id,),
            )
        self.assertTrue(self.store.is_cancelled(self.request_id))
        self.store.mark_cancelled(self.request_id, "worker-a")
        with psycopg.connect(DATABASE_URL) as conn:
            status = conn.execute(
                "SELECT status, lease_expires_at FROM public.yj64_council_api_requests "
                "WHERE request_id = %s",
                (self.request_id,),
            ).fetchone()
        self.assertEqual(status[0], "cancelled")
        self.assertIsNone(status[1])

        # A fresh request exercises terminal result and event persistence.
        second_id = self._insert_request()
        self.store.claim("worker-a", 90)
        self.store.mark_completed(second_id, "worker-a", {"outcome": "consensus"})
        self.store.record_event(second_id, self.agent_id, "council_completed", {"outcome": "consensus"})
        with psycopg.connect(DATABASE_URL) as conn:
            completed = conn.execute(
                "SELECT status, result->>'outcome' FROM public.yj64_council_api_requests "
                "WHERE request_id = %s",
                (second_id,),
            ).fetchone()
        self.assertEqual(completed, ("completed", "consensus"))

    def test_concurrent_claims_do_not_return_the_same_request(self):
        second_id = self._insert_request()
        barrier = threading.Barrier(2)
        claimed = []
        errors = []

        def claim(worker_id):
            try:
                barrier.wait(timeout=5)
                claimed.append(self.store.claim(worker_id, 90))
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=claim, args=("worker-a",)),
            threading.Thread(target=claim, args=("worker-b",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertFalse(errors)
        request_ids = {row["request_id"] for row in claimed if row}
        self.assertEqual(request_ids, {self.request_id, second_id})


if __name__ == "__main__":
    unittest.main()
