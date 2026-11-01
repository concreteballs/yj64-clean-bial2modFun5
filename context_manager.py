"""Provider-neutral, scope-aware context assembly for all router routes."""
from __future__ import annotations

import hashlib
import json
from typing import Any

VALID_MODES = {"memory_only", "memory_recent", "full_history"}
VALID_SCOPES = {"common", "private", "participant_system"}

def _text(value: Any, limit: int = 20000) -> str:
    return str(value or "")[:limit]

def _message(row: dict[str, Any]) -> dict[str, str]:
    role = str(row.get("role", "user"))
    if role not in {"system", "user", "assistant"}:
        role = "user"
    return {"role": role, "content": _text(row.get("content"))}

class ContextManager:
    def build(self, *, route_id: str, mode: str,
              owner_instructions: str = "",
              participant_instructions: str = "",
              participant_memory: str = "",
              semantic_memory: str = "",
              recent_history: list[dict[str, Any]] | None = None,
              full_history: list[dict[str, Any]] | None = None,
              private_history: list[dict[str, Any]] | None = None,
              scope: str = "common",
              authorized: bool = False) -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise ValueError("unknown context mode")
        if scope not in VALID_SCOPES:
            raise ValueError("unknown context scope")
        if scope == "private" and not authorized:
            raise PermissionError("private context requires authorization")
        if not route_id.startswith("route_"):
            raise ValueError("invalid route identity")

        instructions = []
        if owner_instructions.strip():
            instructions.append("OWNER INSTRUCTIONS:\n" + _text(owner_instructions))
        if participant_instructions.strip():
            instructions.append("PARTICIPANT SYSTEM INSTRUCTIONS:\n" +
                                _text(participant_instructions))
        if participant_memory.strip():
            instructions.append("PARTICIPANT MEMORY:\n" + _text(participant_memory))
        if semantic_memory.strip():
            instructions.append("SEMANTIC MEMORY:\n" + _text(semantic_memory))

        if mode == "memory_only":
            history = []
        elif mode == "memory_recent":
            history = recent_history or []
        else:
            history = full_history or []

        # Private requests must never fall back to common history (or vice versa).
        if scope == "private":
            history = private_history or []
        normalized = [_message(x) for x in history if isinstance(x, dict)]
        system_text = "\n\n".join(instructions)
        fingerprint_data = {
            "route_id": route_id, "mode": mode, "scope": scope,
            "system": system_text, "history": normalized,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return {
            "route_id": route_id, "mode": mode, "scope": scope,
            "system_instructions": system_text,
            "messages": normalized,
            "context_fingerprint": fingerprint,
            "source_counts": {"history": len(normalized),
                              "system_sections": len(instructions)},
        }