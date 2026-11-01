"""Q-003 security contract tests; use temporary app data, no network."""
import json
import tempfile
import unittest
from pathlib import Path

from permission_manager import PermissionManager, PermissionDenied
from context_manager import ContextManager

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
            self.pm.require("participant-1", "private.read", "private")

    def test_owner_grant_and_revoke(self):
        self.pm.grant("participant-1", "private.read", "private", self.owner)
        self.pm.require("participant-1", "private.read", "private")
        self.pm.revoke("participant-1", "private.read", "private", self.owner)
        with self.assertRaises(PermissionDenied):
            self.pm.require("participant-1", "private.read", "private")

    def test_corrupt_store_denies(self):
        self.pm.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.pm.require("participant-1", "private.read", "private")

class Q003ContextTests(unittest.TestCase):
    def test_private_requires_authorization(self):
        cm = ContextManager()
        with self.assertRaises(PermissionError):
            cm.build(route_id="route_1", mode="full_history",
                     scope="private", private_history=[{"content":"CANARY"}])

    def test_private_does_not_mix_common_history(self):
        cm = ContextManager()
        result = cm.build(route_id="route_1", mode="full_history",
            scope="private", authorized=True,
            private_history=[{"role":"user","content":"PRIVATE_CANARY"}],
            full_history=[{"role":"user","content":"COMMON_CANARY"}])
        text = json.dumps(result)
        self.assertIn("PRIVATE_CANARY", text)
        self.assertNotIn("COMMON_CANARY", text)

    def test_memory_only_has_no_history(self):
        result = ContextManager().build(route_id="route_2", mode="memory_only",
            recent_history=[{"role":"user","content":"HISTORY_CANARY"}])
        self.assertEqual(result["messages"], [])

if __name__ == "__main__":
    unittest.main()