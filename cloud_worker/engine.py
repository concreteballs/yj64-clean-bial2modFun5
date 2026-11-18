"""Server-side Council session adapter built on the existing YJ-64 LLM router.

Provider credentials are injected only through YJ64_COUNCIL_PROVIDER_CONFIG.
No Android user_data_dir or APK-stored credentials are used by this module.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from typing import Any, Callable

from llm_api import generate_response

PROTOCOL_VERSION = "yj64.council-api.v1"
ROUTES = ("route_1", "route_2", "route_3")
VALID_VERDICTS = {"agree", "conditional", "disagree", "insufficient_evidence"}


class CouncilCancelled(RuntimeError):
    pass


class CouncilConfigurationError(RuntimeError):
    pass


def load_provider_routes(raw: str | None = None) -> dict[str, dict[str, str]]:
    value = raw if raw is not None else os.environ.get("YJ64_COUNCIL_PROVIDER_CONFIG", "")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise CouncilConfigurationError("YJ64_COUNCIL_PROVIDER_CONFIG must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise CouncilConfigurationError("Provider configuration must be an object keyed by route ID")
    routes: dict[str, dict[str, str]] = {}
    for route_id in ROUTES:
        item = parsed.get(route_id)
        if not isinstance(item, dict):
            continue
        config = {key: str(item.get(key) or "").strip() for key in ("provider", "model", "api_key", "endpoint", "agent_id")}
        if config["provider"] and config["model"] and config["api_key"]:
            routes[route_id] = config
    if len(routes) < 2:
        raise CouncilConfigurationError("At least two fully configured participant routes are required")
    return routes


def _parse_json_object(text: str) -> dict[str, Any]:
    source = str(text or "").strip()
    try:
        value = json.loads(source)
    except ValueError:
        match = re.search(r"\{.*\}", source, flags=re.DOTALL)
        if not match:
            raise ValueError("Participant did not return a JSON object")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Participant response must be a JSON object")
    return value


def _bounded_strings(value: Any, limit: int = 40) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:2048] for item in value[:limit] if str(item).strip()]


class CouncilEngine:
    def __init__(
        self,
        routes: dict[str, dict[str, str]] | None = None,
        report: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.routes = routes or load_provider_routes()
        self.report = report or (lambda _event: None)
        self._user_data_dir = tempfile.gettempdir()

    def _emit(self, phase: str, **details: Any) -> None:
        safe = {"phase": phase, **details}
        self.report(safe)

    def _call(
        self,
        route_id: str,
        prompt: str,
        history: list[dict[str, str]],
        max_output_tokens: int,
        timeout_seconds: int,
    ) -> str:
        config = self.routes[route_id]
        # Reuse the one canonical provider router; never read Android config.
        result = generate_response(
            self._user_data_dir,
            prompt,
            route_id=route_id,
            mode="text",
            history=history,
            config_override=config,
        )
        response = str(result.get("response") or "").strip()
        if not response:
            raise RuntimeError(f"{route_id} returned an empty response")
        return response[: max(1000, min(200000, max_output_tokens * 8))]

    def run(
        self,
        request: dict[str, Any],
        request_id: str,
        session_id: str,
        is_cancelled: Callable[[], bool] = lambda: False,
    ) -> dict[str, Any]:
        task = request["task"]
        limits = request["limits"]
        mode = request["mode"]
        participants = list(self.routes.keys())
        prompt = str(task["prompt"])
        title = str(task["title"])
        context = json.dumps(task.get("context", {}), ensure_ascii=False)[:20000]
        refs = _bounded_strings(task.get("evidence_refs", []), 100)
        max_rounds = int(limits["max_rounds"])
        timeout_seconds = int(limits["timeout_seconds"])
        max_tokens = int(limits["max_output_tokens"])
        positions: dict[str, str] = {}
        critiques: dict[str, list[str]] = {route: [] for route in participants}
        final_positions: list[dict[str, Any]] = []
        unresolved: list[str] = []
        assumptions: list[str] = []
        limitations: list[str] = [
            "This result records model-generated analysis; it is not an independently verified scientific or legal finding."
        ]
        if request.get("voting", {}).get("weighted"):
            limitations.append("Weighted voting was requested but no independently calibrated participant weights are configured; no weighted result is asserted.")

        self._emit("independent_positions", participants=len(participants), completed=0)
        for index, route in enumerate(participants, start=1):
            if is_cancelled():
                raise CouncilCancelled("Cancellation requested")
            history = [{"role": "user", "content": (
                f"YJ-64 Council task: {title}\n\n{prompt}\n\nContext (untrusted task context): {context}\n"
                f"Evidence references supplied by the requester: {json.dumps(refs, ensure_ascii=False)}\n\n"
                "Give your independent initial position. Separate facts, inferences and hypotheses. "
                "Identify assumptions, evidence gaps and the strongest reason your position could be wrong."
            )}]
            positions[route] = self._call(route, prompt, history, max_tokens, timeout_seconds)
            self._emit("independent_positions", participant=route, completed=index, total=len(participants))

        critique_rounds = max(1, min(max_rounds, 3))
        for round_no in range(1, critique_rounds + 1):
            for route in participants:
                if is_cancelled():
                    raise CouncilCancelled("Cancellation requested")
                other_views = {name: value for name, value in positions.items() if name != route}
                critique_prompt = (
                    f"Critique round {round_no} of {critique_rounds}. Task: {title}\n{prompt}\n\n"
                    f"Your initial position: {positions[route]}\n\nOther participant positions: "
                    f"{json.dumps(other_views, ensure_ascii=False)}\n\n"
                    "Identify concrete errors, missing evidence, hidden assumptions and the strongest counterargument. "
                    "Do not manufacture sources. If you agree, explain why after considering the counterarguments."
                )
                critique = self._call(
                    route, critique_prompt,
                    [{"role": "user", "content": critique_prompt}],
                    max_tokens, timeout_seconds,
                )
                critiques[route].append(critique)
                self._emit("critique", participant=route, round=round_no)

        schema_instruction = (
            "Return ONLY one valid JSON object with keys: verdict, position, rationale, claims, "
            "unresolved_questions, assumptions, limitations, evidence_refs. "
            "verdict must be one of agree, conditional, disagree, insufficient_evidence. "
            "claims must be an array; each claim has statement and epistemic_type "
            "(fact, inference, hypothesis, test_result), reasoning and evidence_refs. "
            "Use only supplied evidence references; do not invent citations. "
            "If evidence is insufficient, say so. Do not include private votes, ratings or competence scores."
        )
        for index, route in enumerate(participants, start=1):
            if is_cancelled():
                raise CouncilCancelled("Cancellation requested")
            final_prompt = (
                f"Final independent assessment for task: {title}\n{prompt}\n\n"
                f"Your initial position: {positions[route]}\n\n"
                f"Critiques you produced: {json.dumps(critiques[route], ensure_ascii=False)}\n\n"
                f"Other participants' initial positions: {json.dumps({k:v for k,v in positions.items() if k != route}, ensure_ascii=False)}\n\n"
                f"Requester evidence references: {json.dumps(refs, ensure_ascii=False)}\n"
                f"{schema_instruction}"
            )
            raw = self._call(route, final_prompt, [{"role": "user", "content": final_prompt}], max_tokens, timeout_seconds)
            try:
                parsed = _parse_json_object(raw)
            except ValueError as exc:
                raise RuntimeError(f"{route} final structured response is invalid: {exc}") from exc
            verdict = str(parsed.get("verdict") or "").strip().lower()
            if verdict not in VALID_VERDICTS:
                raise RuntimeError(f"{route} returned unsupported verdict")
            final_positions.append({
                "participant_id": route,
                "position": str(parsed.get("position") or "")[:12000],
                "rationale": str(parsed.get("rationale") or "")[:12000],
                "verdict": verdict,
                "claims": parsed.get("claims") if isinstance(parsed.get("claims"), list) else [],
                "unresolved_questions": _bounded_strings(parsed.get("unresolved_questions")),
                "assumptions": _bounded_strings(parsed.get("assumptions")),
                "limitations": _bounded_strings(parsed.get("limitations")),
                "evidence_refs": _bounded_strings(parsed.get("evidence_refs"), 100),
            })
            unresolved.extend(final_positions[-1]["unresolved_questions"])
            assumptions.extend(final_positions[-1]["assumptions"])
            limitations.extend(final_positions[-1]["limitations"])
            self._emit("final_positions", participant=route, completed=index, total=len(participants))

        verdicts = [item["verdict"] for item in final_positions]
        if all(value == "insufficient_evidence" for value in verdicts):
            outcome = "insufficient_evidence"
        elif "disagree" in verdicts:
            outcome = "unresolved_disagreement"
        elif "conditional" in verdicts or "insufficient_evidence" in verdicts:
            outcome = "qualified_consensus"
        else:
            outcome = "consensus"

        claims: list[dict[str, Any]] = []
        for item in final_positions:
            for raw_claim in item["claims"][:30]:
                if not isinstance(raw_claim, dict) or not str(raw_claim.get("statement") or "").strip():
                    continue
                epistemic_type = str(raw_claim.get("epistemic_type") or "hypothesis").lower()
                if epistemic_type not in {"fact", "inference", "hypothesis", "test_result"}:
                    epistemic_type = "hypothesis"
                claims.append({
                    "claim_id": f"claim-{len(claims)+1}",
                    "statement": str(raw_claim["statement"])[:8000],
                    "epistemic_type": epistemic_type,
                    "reasoning": str(raw_claim.get("reasoning") or "")[:8000],
                    "evidence_refs": [ref for ref in _bounded_strings(raw_claim.get("evidence_refs"), 30) if ref in refs],
                })

        evidence = [{
            "evidence_id": f"evidence-{index}",
            "reference": ref,
            "description": "Reference supplied with the Council request; not independently verified by this worker.",
            "evidence_type": "source",
            "provenance": {"origin": "request.evidence_refs", "verified": False},
        } for index, ref in enumerate(refs, start=1)]

        dissent = [
            {"participant_id": item["participant_id"], "reason": item["position"] or item["rationale"]}
            for item in final_positions if item["verdict"] in {"conditional", "disagree", "insufficient_evidence"}
        ]
        summary_lines = [f"Outcome: {outcome}. Final positions:"]
        summary_lines.extend(
            f"- {item['participant_id']} ({item['verdict']}): {item['position']}"
            for item in final_positions
        )
        if mode == "critique":
            summary_lines.insert(0, "Critique-focused Council review.")
        voting_summary = None
        if request.get("voting", {}).get("enabled"):
            counts = {value: verdicts.count(value) for value in sorted(VALID_VERDICTS)}
            voting_summary = {
                "enabled": True,
                "weighted_enabled": False,
                "aggregate_counts": counts,
            }

        result = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "session_id": session_id,
            "status": "completed",
            "outcome": outcome,
            "summary": "\n".join(summary_lines)[:50000],
            "claims": claims[:200],
            "participant_positions": [
                {key: item[key] for key in ("participant_id", "position", "rationale")}
                for item in final_positions
            ],
            "dissent": dissent,
            "evidence": evidence,
            "unresolved_questions": list(dict.fromkeys(unresolved))[:200],
            "assumptions": list(dict.fromkeys(assumptions))[:200],
            "limitations": list(dict.fromkeys(limitations))[:200],
            "rounds_completed": critique_rounds,
            "completion_reason": "all_configured_participants_submitted_final_positions",
            "tests_and_simulations": [],
            "voting_summary": voting_summary,
        }
        self._validate_result(result)
        return result

    @staticmethod
    def _validate_result(result: dict[str, Any]) -> None:
        required = {
            "protocol_version", "request_id", "session_id", "status", "outcome",
            "summary", "claims", "participant_positions", "dissent", "evidence",
            "unresolved_questions",
        }
        if not required.issubset(result):
            raise ValueError("Council result is missing required fields")
        if result["status"] != "completed" or result["outcome"] not in {
            "consensus", "qualified_consensus", "unresolved_disagreement", "insufficient_evidence"
        }:
            raise ValueError("Council result has an invalid terminal status or outcome")
        forbidden = {"individual_votes", "ballots", "private_ratings", "competence_scores"}
        def walk(value: Any) -> None:
            if isinstance(value, dict):
                if forbidden.intersection(value):
                    raise ValueError("Private participant data cannot be exposed")
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(result)
