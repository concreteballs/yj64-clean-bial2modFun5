"""Persistent local chat, skills, and agent workspace for YJ-64."""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any


class ChatWorkspace:
    def __init__(self, user_data_dir: str | Path):
        self.root = Path(user_data_dir) / "yj64-workspace"
        self.root.mkdir(parents=True, exist_ok=True)
        self.chats_dir = self.root / "chats"
        self.agents_dir = self.root / "agents"
        self.histories_dir = self.root / "histories"
        for folder in (self.chats_dir, self.agents_dir, self.histories_dir):
            folder.mkdir(parents=True, exist_ok=True)
        self.skills_path = self.root / "skills.md"
        if not self.skills_path.exists():
            self.skills_path.write_text("# YJ-64 local skills\n", encoding="utf-8")
        self.index_path = self.root / "chats.json"
        if not self.index_path.exists():
            self._write_json(self.index_path, {"chats": []})
        if not self.list_chats():
            self.create_chat("Общий чат")
        self.ensure_chat_files()

    def ensure_chat_files(self) -> None:
        """Create missing chat histories without overwriting existing files."""
        for chat in self.list_chats():
            chat_id = str(chat.get("id", "")).strip()
            if not chat_id:
                continue
            path = self._messages_path(chat_id)
            if not path.exists():
                self._write_json(path, [])

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

    @staticmethod
    def _read_json(path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return fallback

    def list_chats(self) -> list[dict[str, Any]]:
        data = self._read_json(self.index_path, {"chats": []})
        chats = data.get("chats", []) if isinstance(data, dict) else []
        return sorted([item for item in chats if isinstance(item, dict)], key=lambda x: x.get("updated_ms", 0), reverse=True)

    def create_chat(self, title: str, parent_id: str | None = None) -> str:
        chat_id = uuid.uuid4().hex
        chats = self.list_chats()
        chats.append({"id": chat_id, "title": str(title or "Новый чат"), "parent_id": parent_id, "created_ms": int(time.time() * 1000), "updated_ms": int(time.time() * 1000)})
        self._write_json(self.index_path, {"chats": chats})
        self.save_messages(chat_id, [])
        return chat_id

    def _messages_path(self, chat_id: str) -> Path:
        safe_id = "".join(c for c in str(chat_id) if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError("Invalid chat id")
        return self.chats_dir / (safe_id + ".json")

    @staticmethod
    def _normalize_message(message: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(message)
        result["role"] = str(result.get("role", "assistant"))
        result["content"] = str(result.get("content", ""))
        result.setdefault("message_id", uuid.uuid4().hex)
        result.setdefault("timestamp", result.get("timestamp_ms", time.time()))
        result.setdefault("session_id", None)
        result.setdefault("participant_id", None)
        result.setdefault("message_type", "chat")
        return result

    def load_messages(self, chat_id: str) -> list[dict[str, Any]]:
        data = self._read_json(self._messages_path(chat_id), [])
        if not isinstance(data, list):
            return []
        normalized = [self._normalize_message(x) for x in data if isinstance(x, dict)]
        if normalized != data:
            self._write_json(self._messages_path(chat_id), normalized)
        return normalized

    def save_messages(self, chat_id: str, messages: list[dict[str, Any]]) -> None:
        normalized = [self._normalize_message(x) for x in messages if isinstance(x, dict)]
        self._write_json(self._messages_path(chat_id), normalized)
        chats = self.list_chats()
        now = int(time.time() * 1000)
        found = False
        for chat in chats:
            if str(chat.get("id")) == str(chat_id):
                chat["updated_ms"] = now
                if normalized:
                    first = next((m["content"] for m in normalized if m["role"] == "user" and m["content"].strip()), "")
                    if first and chat.get("title") in ("Общий чат", "Новый чат", "Untitled chat"):
                        chat["title"] = first[:48]
                found = True
                break
        if found:
            self._write_json(self.index_path, {"chats": chats})

    @staticmethod
    def _android_owner_identity() -> str | None:
        """Return an app-scoped Android identity; never invent a replacement."""
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            SettingsSecure = autoclass("android.provider.Settings$Secure")
            activity = PythonActivity.mActivity
            if activity is None:
                return None
            android_id = SettingsSecure.getString(
                activity.getContentResolver(), SettingsSecure.ANDROID_ID
            )
            value = str(android_id or "").strip().lower()
            if not value or value in {"9774d56d682e549c", "null", "unknown"}:
                return None
            return "android-owner-v1:" + hashlib.sha256(
                ("yj64-owner-v1:" + value).encode("utf-8")
            ).hexdigest()
        except Exception:
            return None

    def get_local_owner_identity(self) -> dict[str, Any]:
        """Expose identity availability without logging the identity itself."""
        owner_id = self._android_owner_identity()
        return {
            "available": bool(owner_id),
            "owner_id": owner_id,
            "source": "android_id" if owner_id else None,
        }

    def _private_metadata_path(self, name: str) -> Path:
        return self.histories_dir / (self._history_path(name).stem + ".meta.json")

    @staticmethod
    def _validate_requester(requester_id: str | None) -> str:
        requester = str(requester_id or "").strip()
        if not requester:
            raise PermissionError("Private chat access denied: requester identity unavailable")
        return requester

    def load_private_chat_metadata(
        self, name: str, *, requester_id: str
    ) -> dict[str, Any]:
        requester = self._validate_requester(requester_id)
        data = self._read_json(self._private_metadata_path(name), None)
        if not isinstance(data, dict):
            raise PermissionError("Private chat access denied: metadata missing or invalid")
        required = ("chat_id", "visibility", "chat_type", "owner_id", "user_id")
        if any(not str(data.get(key) or "").strip() for key in required):
            raise PermissionError("Private chat access denied: incomplete metadata")
        if data.get("visibility") != "private" or data.get("chat_type") != "personal":
            raise PermissionError("Private chat access denied: not a private personal chat")
        if requester not in {str(data["owner_id"]), str(data["user_id"])}:
            raise PermissionError("Private chat access denied: requester does not own this chat")
        return data

    def create_private_chat_metadata(
        self, name: str, *, chat_id: str, owner_id: str, user_id: str
    ) -> dict[str, Any]:
        """Create metadata only for a genuinely new history, never classify legacy data."""
        values = {
            "chat_id": str(chat_id or "").strip(),
            "visibility": "private",
            "chat_type": "personal",
            "owner_id": str(owner_id or "").strip(),
            "user_id": str(user_id or "").strip(),
        }
        if not all(values[key] for key in ("chat_id", "owner_id", "user_id")):
            raise ValueError("Private chat identity fields must not be empty")
        history_path = self._history_path(name)
        metadata_path = self._private_metadata_path(name)
        if history_path.exists() or metadata_path.exists():
            raise FileExistsError("Existing/legacy history cannot be silently classified as private")
        self._write_json(metadata_path, values)
        return values

    def save_private_named_history(
        self, name: str, history: list[dict[str, Any]], *, requester_id: str
    ) -> None:
        self.load_private_chat_metadata(name, requester_id=requester_id)
        normalized = [
            self._normalize_message(item)
            for item in history
            if isinstance(item, dict)
        ]
        self._write_json(self._history_path(name), normalized)

    def load_private_named_history(
        self, name: str, *, requester_id: str
    ) -> list[dict[str, Any]]:
        self.load_private_chat_metadata(name, requester_id=requester_id)
        data = self._read_json(self._history_path(name), None)
        if not isinstance(data, list):
            raise ValueError("Private chat history is missing or invalid")
        return [
            self._normalize_message(item)
            for item in data
            if isinstance(item, dict)
        ]

    def _history_path(self, name: str) -> Path:
        key = "".join(c for c in str(name) if c.isalnum() or c in "-_ ").strip().replace(" ", "_")
        return self.histories_dir / ((key or "participant") + ".json")

    def load_named_history(self, name: str) -> list[dict[str, Any]]:
        data = self._read_json(self._history_path(name), [])
        if not isinstance(data, list):
            return []
        normalized = [self._normalize_message(x) for x in data if isinstance(x, dict)]
        if normalized != data:
            self._write_json(self._history_path(name), normalized)
        return normalized

    def save_named_history(self, name: str, history: list[dict[str, Any]]) -> None:
        self._write_json(self._history_path(name), [self._normalize_message(x) for x in history if isinstance(x, dict)])

    def read_skills(self) -> str:
        try:
            return self.skills_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def write_skills(self, text: str) -> None:
        self.skills_path.write_text(str(text), encoding="utf-8")

    def _agent_path(self, agent_id: str) -> Path:
        safe_id = "".join(c for c in str(agent_id) if c.isalnum() or c in "-_")
        if not safe_id:
            raise ValueError("Invalid agent id")
        return self.agents_dir / (safe_id + ".json")

    def create_agent(self, name: str, instructions: str, runner: str = "Participant 1") -> dict[str, Any]:
        agent = {"id": uuid.uuid4().hex, "name": str(name), "instructions": str(instructions), "runner": str(runner), "created_ms": int(time.time() * 1000), "private_messages": [], "code_candidate": "", "sandbox_status": "pending", "sandbox_note": ""}
        self.save_agent(agent)
        return agent

    def save_agent(self, agent: dict[str, Any]) -> None:
        if not isinstance(agent, dict) or not agent.get("id"):
            raise ValueError("Agent requires id")
        self._write_json(self._agent_path(str(agent["id"])), agent)

    def load_agent(self, agent_id: str) -> dict[str, Any] | None:
        data = self._read_json(self._agent_path(agent_id), None)
        return data if isinstance(data, dict) else None

    def list_agents(self) -> list[dict[str, Any]]:
        result = []
        for path in self.agents_dir.glob("*.json"):
            data = self._read_json(path, None)
            if isinstance(data, dict):
                result.append(data)
        return sorted(result, key=lambda x: x.get("created_ms", 0), reverse=True)

    def save_agent_message(self, agent_id: str, role: str, content: str) -> None:
        agent = self.load_agent(agent_id)
        if agent is None:
            return
        messages = agent.setdefault("private_messages", [])
        messages.append({"role": str(role), "content": str(content), "timestamp_ms": int(time.time() * 1000)})
        agent["private_messages"] = messages[-1000:]
        self.save_agent(agent)
