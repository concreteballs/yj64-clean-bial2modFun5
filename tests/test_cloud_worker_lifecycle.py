"""Lifecycle tests for the ephemeral Council worker mode."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from cloud_worker import worker


class FakeQueueStore:
    def __init__(self):
        self.heartbeats = []
        self.claims = 0

    def publish_heartbeat(self, worker_id, status, routes):
        self.heartbeats.append((worker_id, status, list(routes)))

    def fail_exhausted_leases(self):
        pass

    def claim(self, worker_id, lease_seconds):
        self.claims += 1
        if self.claims == 1:
            return {"request_id": "bounded-test-request"}
        return None


class WorkerLifecycleTests(unittest.TestCase):
    def test_bounded_worker_drains_claimed_task_and_marks_stopped(self):
        store = FakeQueueStore()
        with (
            patch.dict(os.environ, {"YJ64_WORKER_MAX_TASKS": "1"}),
            patch.object(worker, "load_provider_routes", return_value={
                "route_1": {"provider": "mock"},
                "route_2": {"provider": "mock"},
            }),
            patch.object(worker, "build_queue_store", return_value=store),
            patch.object(worker, "process") as process_mock,
        ):
            worker.main()

        process_mock.assert_called_once()
        self.assertEqual(store.claims, 1)
        self.assertEqual(store.heartbeats[0][1], "running")
        self.assertEqual(store.heartbeats[-1][1], "stopped")
        self.assertEqual(store.heartbeats[-1][2], ["route_1", "route_2"])
        self.assertIsNone(worker.runtime_store)


if __name__ == "__main__":
    unittest.main()
