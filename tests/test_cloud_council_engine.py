import json
import unittest

from cloud_worker.engine import (
    CouncilConfigurationError,
    CouncilEngine,
    _parse_json_object,
    load_provider_routes,
)


class EngineContractTests(unittest.TestCase):
    def test_provider_config_requires_two_participants(self):
        with self.assertRaises(CouncilConfigurationError):
            load_provider_routes(json.dumps({
                "route_1": {"provider": "openai", "model": "x", "api_key": "secret"}
            }))

    def test_provider_config_accepts_two_routes(self):
        routes = load_provider_routes(json.dumps({
            "route_1": {"provider": "openai", "model": "x", "api_key": "secret"},
            "route_2": {"provider": "gemini", "model": "y", "api_key": "secret2"},
        }))
        self.assertEqual(set(routes), {"route_1", "route_2"})

    def test_json_parser_accepts_fenced_or_surrounded_object(self):
        self.assertEqual(_parse_json_object('Result: {"verdict":"agree"}'), {"verdict": "agree"})

    def test_result_validator_rejects_private_fields(self):
        bad = {
            "protocol_version": "yj64.council-api.v1",
            "request_id": "r", "session_id": "s", "status": "completed",
            "outcome": "consensus", "summary": "ok", "claims": [],
            "participant_positions": [], "dissent": [], "evidence": [],
            "unresolved_questions": [], "ballots": [],
        }
        with self.assertRaises(ValueError):
            CouncilEngine._validate_result(bad)

    def test_result_validator_accepts_public_result_shape(self):
        good = {
            "protocol_version": "yj64.council-api.v1",
            "request_id": "r", "session_id": "s", "status": "completed",
            "outcome": "consensus", "summary": "ok", "claims": [],
            "participant_positions": [], "dissent": [], "evidence": [],
            "unresolved_questions": [],
        }
        CouncilEngine._validate_result(good)


if __name__ == "__main__":
    unittest.main()
