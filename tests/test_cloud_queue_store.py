"""Tests for the queue persistence boundary and Supabase compatibility adapter."""
import unittest
from unittest.mock import MagicMock

from cloud_worker.queue_store import SupabaseQueueStore


class QueueStoreAdapterTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.store = SupabaseQueueStore(self.client)

    def test_claim_returns_first_claimed_row(self):
        expected = {"request_id": "r-1", "status": "running"}
        self.client.rpc.return_value.execute.return_value.data = [expected]
        self.assertEqual(self.store.claim("worker-1", 180), expected)
        self.client.rpc.assert_called_once_with(
            "yj64_claim_council_api_request",
            {"p_worker_id": "worker-1", "p_lease_seconds": 180},
        )

    def test_claim_returns_none_when_queue_is_empty(self):
        self.client.rpc.return_value.execute.return_value.data = []
        self.assertIsNone(self.store.claim("worker-1", 180))

    def test_claim_accepts_single_row_rpc_response(self):
        expected = {"request_id": "r-1"}
        self.client.rpc.return_value.execute.return_value.data = expected
        self.assertEqual(self.store.claim("worker-1", 180), expected)

    def test_cancellation_reads_request_flag_and_status(self):
        query = self.client.table.return_value.select.return_value.eq.return_value.single.return_value.execute
        query.return_value.data = {"cancel_requested": True, "status": "running"}
        self.assertTrue(self.store.is_cancelled("r-1"))

    def test_progress_update_is_fenced_to_current_worker_and_running_state(self):
        self.store.update_progress("r-1", "worker-1", {"phase": "critique"})
        table = self.client.table
        table.assert_called_with("yj64_council_api_requests")
        table.return_value.update.assert_called_once()
        table.return_value.update.return_value.eq.assert_any_call("request_id", "r-1")
        table.return_value.update.return_value.eq.return_value.eq.assert_called_with(
            "status", "running"
        )

    def test_terminal_completion_clears_lease_and_errors(self):
        self.store.mark_completed("r-1", "worker-1", {"outcome": "consensus"})
        payload = self.client.table.return_value.update.call_args.args[0]
        self.assertEqual(payload["status"], "completed")
        self.assertIsNone(payload["lease_expires_at"])
        self.assertIsNone(payload["error_code"])
        self.assertEqual(payload["result"], {"outcome": "consensus"})

    def test_event_persistence_uses_existing_event_table_contract(self):
        self.store.record_event("r-1", "agent-1", "council_completed", {"outcome": "consensus"})
        self.client.table.assert_called_with("yj64_council_api_events")
        payload = self.client.table.return_value.insert.call_args.args[0]
        self.assertEqual(payload["request_id"], "r-1")
        self.assertEqual(payload["agent_id"], "agent-1")
        self.assertEqual(payload["event_type"], "council_completed")


if __name__ == "__main__":
    unittest.main()
