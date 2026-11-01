"""Q-003 permission and context-isolation contract tests; no network access."""
import tempfile
import unittest
from pathlib import Path

from context_manager import ContextManager
from permission_manager import PermissionDenied, PermissionManager


class Q003PermissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.owner = PermissionManager.load_or_create_owner_id(self.root)
        self.pm = PermissionManager(self.root, self.owner)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_deny(self):
        with self.assertRaises(PermissionDenied):
            self.pm.require(
                requester_id=self.owner,
                resource="private-chat:chat-1",
                action="read",
                scope="chat-1",
            )

    def test_owner_grant_and_revoke(self):
        grant_id = self.pm.issue_grant(
            actor_id=self.owner,
            subject_id=self.owner,
            resource="private-chat:chat-1",
            action="read",
            ttl_seconds=60,
            scope="chat-1",
        )
        self.pm.require(
            requester_id=self.owner,
            resource="private-chat:chat-1",
            action="read",
            scope="chat-1",
        )
        self.assertTrue(self.pm.revoke_grant(actor_id=self.owner, grant_id=grant_id))
        with self.assertRaises(PermissionDenied):
            self.pm.require(
                requester_id=self.owner,
                resource="private-chat:chat-1",
                action="read",
                scope="chat-1",
            )

    def test_corrupt_store_fails_closed(self):
        self.pm.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(IOError):
            PermissionManager(self.root, self.owner)


class Q003ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.owner = PermissionManager.load_or_create_owner_id(self.root)
        self.pm = PermissionManager(self.root, self.owner)
        self.context = ContextManager(self.pm, self.owner)

    def tearDown(self):
        self.tmp.cleanup()

    def test_private_requires_real_permission_grant(self):
        with self.assertRaises(PermissionDenied):
            self.context.build(
                route_id="route_1",
                mode="full_history",
                scope="private",
                requester_id=self.owner,
                chat_id="chat-1",
                private_history=[{"role": "user", "content": "PRIVATE_CANARY"}],
            )

    def test_private_context_excludes_common_history_after_grant(self):
        self.pm.issue_grant(
            actor_id=self.owner,
            subject_id=self.owner,
            resource="private-chat:chat-1",
            action="read",
            ttl_seconds=60,
            scope="chat-1",
        )
        result = self.context.build(
            route_id="route_1",
            mode="full_history",
            scope="private",
            requester_id=self.owner,
            chat_id="chat-1",
            private_history=[{"role": "user", "content": "PRIVATE_CANARY"}],
            full_history=[{"role": "user", "content": "COMMON_CANARY"}],
        )
        rendered = str(result)
        self.assertIn("PRIVATE_CANARY", rendered)
        self.assertNotIn("COMMON_CANARY", rendered)

    def test_participant_system_scope_requires_grant(self):
        with self.assertRaises(PermissionDenied):
            self.context.build(
                route_id="route_2",
                mode="full_history",
                scope="participant_system",
                requester_id=self.owner,
                participant_id="route_2",
                participant_history=[{"role": "user", "content": "SYSTEM_CANARY"}],
            )

    def test_memory_only_has_no_history(self):
        result = self.context.build(
            route_id="route_2",
            mode="memory_only",
            recent_history=[{"role": "user", "content": "HISTORY_CANARY"}],
        )
        self.assertEqual(result["messages"], [])


if __name__ == "__main__":
    unittest.main()