"""Provenance-aware semantic memory; raw chat history remains authoritative."""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterable


class SemanticMemory:
    SCHEMA = "yj64.semantic-memory.v1"
    TYPES = frozenset({
        "fact", "decision", "preference", "hypothesis", "question", "conflict"
    })

    def __init__(self, user_data_dir: str | Path, *, clock=time.time) -> None:
        self.path = Path(user_data_dir) / "yj64-workspace" / "semantic-memory.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": self.SCHEMA, "items": [], "sources": {}}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise IOError("Semantic memory is unreadable; refusing to overwrite") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != self.SCHEMA
            or not isinstance(value.get("items"), list)
            or not isinstance(value.get("sources"), dict)
        ):
            raise IOError("Invalid semantic memory schema")
        return value

    @staticmethod
    def _digest(message: dict[str, Any]) -> str:
        payload = json.dumps(message, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _save(self) -> None:
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                json.dump(self.state, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)

    def sync_sources(
        self,
        messages: Iterable[dict[str, Any]],
        *,
        scope: str,
        participant_id: str | None = None,
    ) -> dict[str, list[str]]:
        scope_key = str(scope).strip()
        if not scope_key:
            raise ValueError("scope is required")
        current: dict[str, str] = {}
        for message in messages:
            if not isinstance(message, dict):
                continue
            message_id = str(message.get("message_id") or "").strip()
            if not message_id:
                continue
            current[message_id] = self._digest(message)
        key = scope_key + ":" + str(participant_id or "common")
        previous = self.state["sources"].get(key, {})
        if not isinstance(previous, dict):
            previous = {}
        old_ids, new_ids = set(previous), set(current)
        added = sorted(new_ids - old_ids)
        changed = sorted(mid for mid in new_ids & old_ids if current[mid] != previous[mid])
        deleted = sorted(old_ids - new_ids)
        invalidated = set(changed + deleted)
        if invalidated:
            for item in self.state["items"]:
                sources = set(item.get("source_message_ids") or [])
                if sources & invalidated:
                    item["status"] = "stale"
                    item["stale_reason"] = (
                        "source_changed" if sources & set(changed) else "source_deleted"
                    )
                    item["updated_at"] = self.clock()
        self.state["sources"][key] = current
        self._save()
        return {"added": added, "changed": changed, "deleted": deleted}

    def upsert(
        self,
        *,
        item_type: str,
        text: str,
        source_message_ids: list[str],
        scope: str,
        participant_id: str | None = None,
        confidence: float,
    ) -> str:
        if item_type not in self.TYPES:
            raise ValueError("Unsupported semantic memory item type")
        body = str(text).strip()
        sources = sorted({str(x).strip() for x in source_message_ids if str(x).strip()})
        scope_key = str(scope).strip()
        if not body or not sources or not scope_key:
            raise ValueError("text, source_message_ids and scope are required")
        if isinstance(confidence, bool) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        now = self.clock()
        item_id = uuid.uuid4().hex
        record = {
            "id": item_id,
            "type": item_type,
            "text": body,
            "confidence": float(confidence),
            "source_message_ids": sources,
            "participant_id": str(participant_id) if participant_id else None,
            "scope": scope_key,
            "created_at": now,
            "updated_at": now,
            "status": "active",
        }
        self.state["items"].append(record)
        self._save()
        return item_id

    def list_items(
        self, *, scope: str, participant_id: str | None = None,
        include_stale: bool = False,
    ) -> list[dict[str, Any]]:
        result = []
        for item in self.state["items"]:
            if item.get("scope") != scope:
                continue
            if item.get("participant_id") != participant_id:
                continue
            if not include_stale and item.get("status") != "active":
                continue
            result.append(dict(item))
        return result