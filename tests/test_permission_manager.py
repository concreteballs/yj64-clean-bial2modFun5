import json
import tempfile
import unittest
from pathlib import Path

from permission_manager import PermissionDenied, PermissionManager


class PermissionManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = [1000.0]
        self.owner = "owner-local-1"
        self.manager = PermissionManager(
            self.temp.name, self.owner, clock=lambda: self.now[0]
        )

    def tearDown(self):
        self.temp.cleanup()

    def grant(self, **overrides):
        values = {
            "actor_id": self.owner,
            "subject_id": "participant-1",
            "resource": "private-chat:chat-1",
            "action": "read",
            "ttl_seconds": 60,
            "scope": "chat-1",
        }
        values.update(overrides)
        return self.manager.issue_grant(**values)

    def test_owner_identity_is_stable(self):
        first = PermissionManager.load_or_create_owner_id(self.temp.name)
        second = PermissionManager.load_or_create_owner_id(self.temp.name)
        self.assertEqual(first, second)
        self.assertTrue(first)

    def test_default_deny(self):
        with self.assertRaises(PermissionDenied):
            self.manager.require(
                requester_id="participant-1",
                resource="private-chat:chat-1",
                action="read",
                scope="chat-1",
            )

    def test_exact_scope_is_required(self):
        self.grant()
        with self.assertRaises(PermissionDenied):
            self.manager.require(
                requester_id="participant-1",
                resource="private-chat:chat-1",
                action="read",
                scope="chat-2",
            )

    def test_expired_grant_is_denied(self):
        self.grant()
        self.now[0] += 61
        with self.assertRaises(PermissionDenied):
            self.manager.require(
                requester_id="participant-1",
                resource="private-chat:chat-1",
                action="read",
                scope="chat-1",
            )

    def test_revocation_is_immediate(self):
        grant_id = self.grant()
        self.assertTrue(self.manager.revoke_grant(
            actor_id=self.owner, grant_id=grant_id
        ))
        with self.assertRaises(PermissionDenied):
            self.manager.require(
                requester_id="participant-1",
                resource="private-chat:chat-1",
                action="read",
                scope="chat-1",
            )

    def test_non_owner_cannot_issue_or_revoke(self):
        with self.assertRaises(PermissionDenied):
            self.grant(actor_id="participant-1")
        grant_id = self.grant()
        with self.assertRaises(PermissionDenied):
            self.manager.revoke_grant(
                actor_id="participant-1", grant_id=grant_id
            )

    def test_different_subject_and_action_are_denied(self):
        self.grant()
        for subject, action in (("participant-2", "read"), ("participant-1", "write")):
            with self.assertRaises(PermissionDenied):
                self.manager.require(
                    requester_id=subject,
                    resource="private-chat:chat-1",
                    action=action,
                    scope="chat-1",
                )

    def test_corrupt_store_fails_closed(self):
        self.manager.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(IOError):
            PermissionManager(self.temp.name, self.owner)

    def test_audit_does_not_store_payload_or_secret(self):
        self.grant()
        self.manager.require(
            requester_id="participant-1",
            resource="private-chat:chat-1",
            action="read",
            scope="chat-1",
        )
        audit = self.manager.audit_path.read_text(encoding="utf-8")
        self.assertNotIn("api_key", audit)
        self.assertNotIn("private message body", audit)
        records = [json.loads(line) for line in audit.splitlines()]
        self.assertTrue(any(item["decision"] == "allow" for item in records))


if __name__ == "__main__":
    unittest.main()