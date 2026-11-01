"""Default-deny permission policy for YJ-64 local operations.

This is an application policy layer, not an OS security boundary. Code
running with the same process privileges must not be treated as hostile
sandboxed code.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any


class PermissionDenied(PermissionError):
    """Raised when an operation has no currently valid grant."""


class PermissionManager:
    @classmethod
    def load_or_create_owner_id(cls, user_data_dir: str | Path) -> str:
        identity_path = (
            Path(user_data_dir) / "yj64-workspace" / "owner-identity.json"
        )
        identity_path.parent.mkdir(parents=True, exist_ok=True)
        if identity_path.exists():
            try:
                value = json.loads(identity_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError) as exc:
                raise IOError("Owner identity is unreadable; refusing to replace it") from exc
            owner_id = str(value.get("owner_id") or "").strip() if isinstance(value, dict) else ""
            if not owner_id or value.get("schema") != "yj64.owner-identity.v1":
                raise IOError("Owner identity has an invalid schema")
            return owner_id
        owner_id = uuid.uuid4().hex
        cls._atomic_write(
            identity_path,
            json.dumps(
                {"schema": "yj64.owner-identity.v1", "owner_id": owner_id},
                ensure_ascii=False,
                indent=2,
            ),
        )
        return owner_id

    ACTIONS = frozenset({
        "read", "write", "commit", "build", "publish", "service_management"
    })
    SCHEMA = "yj64.permissions.v1"

    def __init__(
        self,
        user_data_dir: str | Path,
        owner_id: str,
        *,
        clock=time.time,
    ) -> None:
        self.root = Path(user_data_dir) / "yj64-workspace"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "permissions.json"
        self.audit_path = self.root / "permission-audit.jsonl"
        self.owner_id = str(owner_id).strip()
        if not self.owner_id:
            raise ValueError("owner_id is required")
        self._clock = clock
        self._lock = threading.RLock()
        self._state = self._load()

    @staticmethod
    def _atomic_write(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema": self.SCHEMA, "grants": []}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise IOError("Permission store is unreadable; refusing access") from exc
        if (
            not isinstance(value, dict)
            or value.get("schema") != self.SCHEMA
            or not isinstance(value.get("grants"), list)
        ):
            raise IOError("Permission store has an invalid schema; refusing access")
        return value

    def _save(self) -> None:
        self._atomic_write(
            self.path, json.dumps(self._state, ensure_ascii=False, indent=2)
        )

    def _audit(
        self, decision: str, *, subject_id: str, resource: str,
        action: str, reason: str, grant_id: str | None = None,
    ) -> None:
        record = {
            "schema": self.SCHEMA,
            "timestamp_ms": int(self._clock() * 1000),
            "decision": decision,
            "subject_id": subject_id,
            "resource": resource,
            "action": action,
            "reason": reason,
            "grant_id": grant_id,
        }
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def issue_grant(
        self,
        *,
        actor_id: str,
        subject_id: str,
        resource: str,
        action: str,
        ttl_seconds: int,
        scope: str,
    ) -> str:
        actor = str(actor_id).strip()
        subject = str(subject_id).strip()
        resource_key = str(resource).strip()
        scope_key = str(scope).strip()
        if actor != self.owner_id:
            raise PermissionDenied("Only the owner may issue a grant")
        if not subject or not resource_key or not scope_key:
            raise ValueError("subject_id, resource and scope are required")
        if action not in self.ACTIONS:
            raise ValueError("Unsupported permission action")
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
            raise ValueError("ttl_seconds must be an integer")
        if ttl_seconds <= 0 or ttl_seconds > 31 * 24 * 60 * 60:
            raise ValueError("ttl_seconds must be between 1 second and 31 days")
        now = self._clock()
        grant = {
            "grant_id": uuid.uuid4().hex,
            "subject_id": subject,
            "resource": resource_key,
            "action": action,
            "scope": scope_key,
            "created_by": actor,
            "created_at": now,
            "expires_at": now + ttl_seconds,
            "revoked_at": None,
        }
        with self._lock:
            self._state["grants"].append(grant)
            self._save()
            self._audit(
                "grant_issued", subject_id=subject, resource=resource_key,
                action=action, reason="owner_grant", grant_id=grant["grant_id"],
            )
        return grant["grant_id"]

    def revoke_grant(self, *, actor_id: str, grant_id: str) -> bool:
        if str(actor_id).strip() != self.owner_id:
            raise PermissionDenied("Only the owner may revoke a grant")
        with self._lock:
            for grant in self._state["grants"]:
                if grant.get("grant_id") == str(grant_id) and grant.get("revoked_at") is None:
                    grant["revoked_at"] = self._clock()
                    self._save()
                    self._audit(
                        "grant_revoked",
                        subject_id=str(grant.get("subject_id") or ""),
                        resource=str(grant.get("resource") or ""),
                        action=str(grant.get("action") or ""),
                        reason="owner_revocation",
                        grant_id=str(grant_id),
                    )
                    return True
        return False

    def check(
        self,
        *,
        requester_id: str,
        resource: str,
        action: str,
        scope: str,
    ) -> bool:
        subject = str(requester_id).strip()
        resource_key = str(resource).strip()
        scope_key = str(scope).strip()
        if not subject or not resource_key or not scope_key or action not in self.ACTIONS:
            self._audit(
                "deny", subject_id=subject, resource=resource_key,
                action=str(action), reason="invalid_request",
            )
            raise PermissionDenied("Invalid or incomplete permission request")
        now = self._clock()
        with self._lock:
            matches = [
                grant for grant in self._state["grants"]
                if grant.get("subject_id") == subject
                and grant.get("resource") == resource_key
                and grant.get("action") == action
                and grant.get("scope") == scope_key
                and grant.get("revoked_at") is None
                and isinstance(grant.get("expires_at"), (int, float))
                and now < grant["expires_at"]
            ]
            if not matches:
                self._audit(
                    "deny", subject_id=subject, resource=resource_key,
                    action=action, reason="no_active_matching_grant",
                )
                raise PermissionDenied(
                    f"Denied {action} on {resource_key}: no active grant"
                )
            selected = max(matches, key=lambda item: float(item["expires_at"]))
            self._audit(
                "allow", subject_id=subject, resource=resource_key,
                action=action, reason="active_grant",
                grant_id=str(selected["grant_id"]),
            )
            return True

    def require(self, **request: Any) -> None:
        self.check(**request)

    def list_active_grants(self, *, actor_id: str) -> list[dict[str, Any]]:
        if str(actor_id).strip() != self.owner_id:
            raise PermissionDenied("Only the owner may inspect grants")
        now = self._clock()
        with self._lock:
            return [
                dict(grant) for grant in self._state["grants"]
                if grant.get("revoked_at") is None
                and isinstance(grant.get("expires_at"), (int, float))
                and now < grant["expires_at"]
            ]