"""Scope-aware context assembly with enforced private access checks."""
from __future__ import annotations

import hashlib
import json
from typing import Any


VALID_MODES = {"memory_only", "memory_recent", "full_history"}
VALID_SCOPES = {"common", "private", "participant_system"}


def _text(value: Any, limit: int = 20000) -> str:
    result = str(value or "")
    if len(result) > limit:
        raise ValueError("context text exceeds the configured character limit")
    return result


def _message(row: dict[str, Any]) -> dict[str, str]:
    role = str(row.get("role", "user"))
    if role not in {"system", "user", "assistant"}:
        role = "user"
    return {"role": role, "content": _text(row.get("content"))}


class ContextManager:
    """Builds isolated context; private access is checked against PermissionManager."""

    def __init__(self, permission_manager: Any = None, owner_id: str | None = None):
        self.permission_manager = permission_manager
        self.owner_id = str(owner_id or "").strip()

    def _require_scope(self, *, requester_id: str | None, resource: str, scope: str) -> None:
        if self.permission_manager is None:
            raise PermissionError("permission manager is unavailable; private context denied")
        if not requester_id:
            raise PermissionError("requester identity is required")
        self.permission_manager.require(
            requester_id=str(requester_id),
            resource=resource,
            action="read",
            scope=scope,
        )

    def build(
        self,
        *,
        route_id: str,
        mode: str,
        owner_instructions: str = "",
        participant_instructions: str = "",
        participant_memory: str = "",
        semantic_memory: str = "",
        recent_history: list[dict[str, Any]] | None = None,
        full_history: list[dict[str, Any]] | None = None,
        private_history: list[dict[str, Any]] | None = None,
        participant_history: list[dict[str, Any]] | None = None,
        scope: str = "common",
        requester_id: str | None = None,
        chat_id: str | None = None,
        participant_id: str | None = None,
    ) -> dict[str, Any]:
        if mode not in VALID_MODES:
            raise ValueError("unknown context mode")
        if scope not in VALID_SCOPES:
            raise ValueError("unknown context scope")
        if not route_id.startswith("route_") and route_id != "route_owner":
            raise ValueError("invalid route identity")

        if scope == "private":
            selected_chat = str(chat_id or "").strip()
            if not selected_chat:
                raise PermissionError("private context requires a chat_id")
            self._require_scope(
                requester_id=requester_id,
                resource="private-chat:" + selected_chat,
                scope=selected_chat,
            )
        elif scope == "participant_system":
            selected_participant = str(participant_id or "").strip()
            if not selected_participant:
                raise PermissionError("participant system context requires participant_id")
            self._require_scope(
                requester_id=requester_id,
                resource="system-chat:" + selected_participant,
                scope=selected_participant,
            )

        instructions = []
        if str(owner_instructions or "").strip():
            instructions.append("OWNER INSTRUCTIONS:\n" + _text(owner_instructions))
        if str(participant_instructions or "").strip():
            instructions.append(
                "PARTICIPANT SYSTEM INSTRUCTIONS:\n" + _text(participant_instructions)
            )
        if str(participant_memory or "").strip():
            instructions.append("PARTICIPANT MEMORY:\n" + _text(participant_memory))
        if str(semantic_memory or "").strip():
            instructions.append("SEMANTIC MEMORY:\n" + _text(semantic_memory))

        if mode == "memory_only":
            history = []
        elif mode == "memory_recent":
            history = list(recent_history or [])
        else:
            history = list(full_history or [])

        if scope == "private":
            history = list(private_history or [])
        elif scope == "participant_system":
            history = list(participant_history or [])

        normalized = [_message(x) for x in history if isinstance(x, dict)]
        system_text = "\n\n".join(instructions)
        fingerprint_data = {
            "route_id": route_id,
            "mode": mode,
            "scope": scope,
            "chat_id": chat_id if scope == "private" else None,
            "participant_id": participant_id if scope == "participant_system" else None,
            "system": system_text,
            "history": normalized,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_data, sort_keys=True, ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        return {
            "route_id": route_id,
            "mode": mode,
            "scope": scope,
            "system_instructions": system_text,
            "messages": normalized,
            "context_fingerprint": fingerprint,
            "source_counts": {
                "history": len(normalized),
                "system_sections": len(instructions),
            },
        }