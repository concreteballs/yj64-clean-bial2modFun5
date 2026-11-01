"""Owner-managed system instructions and isolated participant system chats."""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


class SystemChatAccessDenied(PermissionError):
    pass


class SystemChatStore:
    SCHEMA = "yj64.system-chat.v1"

    def __init__(self, user_data_dir: str | Path, owner_id: str) -> None:
        self.root = Path(user_data_dir) / "yj64-workspace" / "system-chats"
        self.root.mkdir(parents=True, exist_ok=True)
        self.owner_id = str(owner_id).strip()
        if not self.owner_id:
            raise ValueError("owner_id is required")

    @staticmethod
    def _safe_id(value: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", str(value))
        if not safe:
            raise ValueError("Invalid participant_id")
        return safe

    def _path(self, participant_id: str) -> Path:
        return self.root / (self._safe_id(participant_id) + ".json")

    def _read(self, participant_id: str) -> dict[str, Any]:
        path = self._path(participant_id)
        if not path.exists():
            return {
                "schema": self.SCHEMA,
                "participant_id": self._safe_id(participant_id),
                "system_instructions": "",
                "messages": [],
            }
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise IOError("System chat is unreadable; refusing to overwrite") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != self.SCHEMA
            or value.get("participant_id") != self._safe_id(participant_id)
            or not isinstance(value.get("messages"), list)
            or not isinstance(value.get("system_instructions"), str)
        ):
            raise IOError("Invalid system chat schema")
        return value

    def _write(self, participant_id: str, value: dict[str, Any]) -> None:
        path = self._path(participant_id)
        temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def set_system_instructions(
        self, *, actor_id: str, participant_id: str, instructions: str
    ) -> None:
        if str(actor_id).strip() != self.owner_id:
            raise SystemChatAccessDenied("Only the owner may edit system instructions")
        data = self._read(participant_id)
        data["system_instructions"] = str(instructions)
        data["instructions_updated_at"] = time.time()
        self._write(participant_id, data)

    def append_message(
        self, *, actor_id: str, participant_id: str, role: str, content: str
    ) -> None:
        actor = str(actor_id).strip()
        pid = self._safe_id(participant_id)
        if actor not in (self.owner_id, pid):
            raise SystemChatAccessDenied("Actor cannot write another participant's system chat")
        if role not in ("user", "assistant", "system"):
            raise ValueError("Unsupported system-chat role")
        if role == "system" and actor != self.owner_id:
            raise SystemChatAccessDenied("Only the owner may append a system message")
        data = self._read(pid)
        data["messages"].append({
            "message_id": uuid.uuid4().hex,
            "actor_id": actor,
            "role": role,
            "content": str(content),
            "timestamp_ms": int(time.time() * 1000),
        })
        self._write(pid, data)

    def load_for_participant(
        self, *, actor_id: str, participant_id: str
    ) -> dict[str, Any]:
        actor = str(actor_id).strip()
        pid = self._safe_id(participant_id)
        if actor not in (self.owner_id, pid):
            raise SystemChatAccessDenied("Actor cannot read another participant's system chat")
        data = self._read(pid)
        return {
            "participant_id": pid,
            "system_instructions": data["system_instructions"],
            "messages": [dict(item) for item in data["messages"]],
            "provenance": {
                "instructions_source": "owner",
                "chat_source": "participant_system_chat",
                "participant_id": pid,
            },
        }