import unittest

from cloud_worker.api import VERSION, has_private_fields, sha256, stable, validate_request


def valid_body():
    return {
        "protocol_version": VERSION,
        "agent_id": "test-agent",
        "correlation_id": "corr-12345678",
        "idempotency_key": "idem-12345678",
        "mode": "consensus",
        "task": {
            "title": "Test task",
            "prompt": "Assess this test.",
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


class PortableCouncilApiValidationTests(unittest.TestCase):
    def test_valid_request_matches_public_contract(self):
        self.assertIsNone(validate_request(valid_body()))

    def test_rejects_unknown_fields_and_invalid_limits(self):
        body = valid_body()
        body["unexpected"] = True
        self.assertEqual(validate_request(body), "unknown_request_field")
        body = valid_body()
        body["limits"]["max_rounds"] = 11
        self.assertEqual(validate_request(body), "invalid_max_rounds")

    def test_rejects_boolean_for_integer_critique_limit(self):
        body = valid_body()
        body["limits"]["minimum_critique_rounds"] = True
        self.assertEqual(validate_request(body), "invalid_critique_limits")

    def test_rejects_invalid_context_and_missing_evidence_array(self):
        body = valid_body()
        body["task"]["context"] = []
        self.assertEqual(validate_request(body), "invalid_task_context")
        body = valid_body()
        del body["task"]["evidence_refs"]
        self.assertEqual(validate_request(body), "invalid_evidence_refs")

    def test_stable_hash_is_order_independent_for_object_keys(self):
        self.assertEqual(stable({"b": 2, "a": 1}), stable({"a": 1, "b": 2}))
        self.assertEqual(sha256(stable({"a": 1})), sha256(stable({"a": 1})))

    def test_private_result_fields_are_rejected_recursively(self):
        self.assertTrue(has_private_fields({"nested": [{"private_ratings": [1]}]}))
        self.assertFalse(has_private_fields({"claims": [{"statement": "public"}]}))


if __name__ == "__main__":
    unittest.main()
