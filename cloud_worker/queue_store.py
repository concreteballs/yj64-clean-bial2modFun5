"""Queue persistence boundary for the Council worker.

The worker depends on this contract, not on a database SDK. The first
implementation deliberately preserves the existing Supabase schema/RPC.
A standard PostgreSQL implementation will be added against the verified
migration schema; it must pass the same contract tests before activation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


class QueueStore(Protocol):
    def load_request(self, request_id: str) -> dict[str, Any]: ...
    def is_cancelled(self, request_id: str) -> bool: ...
    def update_progress(self, request_id: str, worker_id: str, progress: dict[str, Any]) -> None: ...
    def renew_lease(self, request_id: str, worker_id: str, lease_seconds: int) -> None: ...
    def mark_cancelled(self, request_id: str, worker_id: str) -> None: ...
    def mark_completed(self, request_id: str, worker_id: str, result: dict[str, Any]) -> None: ...
    def record_event(self, request_id: str, agent_id: str, event_type: str, details: dict[str, Any]) -> None: ...
    def record_attempt_failure(self, request_id: str, worker_id: str, message: str) -> None: ...
    def fail_exhausted_leases(self) -> None: ...
    def publish_heartbeat(self, worker_id: str, status: str, routes: list[str]) -> None: ...
    def claim(self, worker_id: str, lease_seconds: int) -> dict[str, Any] | None: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseQueueStore:
    """Compatibility adapter for the currently deployed Supabase schema."""

    def __init__(self, client: Any) -> None:
        self._db = client

    def load_request(self, request_id: str) -> dict[str, Any]:
        response = self._db.table("yj64_council_api_requests").select("*").eq(
            "request_id", request_id
        ).single().execute()
        return response.data

    def is_cancelled(self, request_id: str) -> bool:
        row = self._db.table("yj64_council_api_requests").select(
            "cancel_requested,status"
        ).eq("request_id", request_id).single().execute().data
        return bool(row.get("cancel_requested")) or row.get("status") == "cancelled"

    def update_progress(self, request_id: str, worker_id: str, progress: dict[str, Any]) -> None:
        self._db.table("yj64_council_api_requests").update({
            "progress": progress, "updated_at": _utc_now()
        }).eq("request_id", request_id).eq("worker_id", worker_id).eq(
            "status", "running"
        ).execute()

    def renew_lease(self, request_id: str, worker_id: str, lease_seconds: int) -> None:
        expires = (datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)).isoformat()
        self._db.table("yj64_council_api_requests").update({
            "lease_expires_at": expires, "updated_at": _utc_now()
        }).eq("request_id", request_id).eq("worker_id", worker_id).eq(
            "status", "running"
        ).execute()

    def mark_cancelled(self, request_id: str, worker_id: str) -> None:
        self._db.table("yj64_council_api_requests").update({
            "status": "cancelled", "completed_at": _utc_now(),
            "updated_at": _utc_now(), "lease_expires_at": None,
        }).eq("request_id", request_id).eq("worker_id", worker_id).eq(
            "status", "running"
        ).execute()

    def mark_completed(self, request_id: str, worker_id: str, result: dict[str, Any]) -> None:
        self._db.table("yj64_council_api_requests").update({
            "status": "completed", "result": result, "progress": {"phase": "completed"},
            "completed_at": _utc_now(), "updated_at": _utc_now(), "lease_expires_at": None,
            "error_code": None, "error_message": None,
        }).eq("request_id", request_id).eq("worker_id", worker_id).eq(
            "status", "running"
        ).execute()

    def record_event(self, request_id: str, agent_id: str, event_type: str, details: dict[str, Any]) -> None:
        self._db.table("yj64_council_api_events").insert({
            "request_id": request_id, "agent_id": agent_id,
            "event_type": event_type, "details": details,
        }).execute()

    def record_attempt_failure(self, request_id: str, worker_id: str, message: str) -> None:
        self._db.table("yj64_council_api_requests").update({
            "error_code": "worker_attempt_failed",
            "error_message": message[:2000],
            "lease_expires_at": _utc_now(),
            "updated_at": _utc_now(),
        }).eq("request_id", request_id).eq("worker_id", worker_id).eq(
            "status", "running"
        ).execute()

    def fail_exhausted_leases(self) -> None:
        now = _utc_now()
        expired = self._db.table("yj64_council_api_requests").select(
            "request_id,attempts,max_attempts"
        ).eq("status", "running").lt("lease_expires_at", now).execute().data or []
        for row in expired:
            if int(row["attempts"]) >= int(row["max_attempts"]):
                self._db.table("yj64_council_api_requests").update({
                    "status": "failed", "error_code": "worker_retries_exhausted",
                    "error_message": "Worker lease expired after the maximum number of attempts.",
                    "completed_at": now, "updated_at": now, "lease_expires_at": None,
                }).eq("request_id", row["request_id"]).eq("status", "running").execute()

    def publish_heartbeat(self, worker_id: str, status: str, routes: list[str]) -> None:
        now = _utc_now()
        self._db.table("yj64_council_api_workers").upsert({
            "worker_id": worker_id, "status": status,
            "version": "yj64-council-worker/1.0.0", "routes": routes,
            "last_seen_at": now, "updated_at": now,
        }).execute()

    def claim(self, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        claimed = self._db.rpc("yj64_claim_council_api_request", {
            "p_worker_id": worker_id, "p_lease_seconds": lease_seconds,
        }).execute().data or []
        if not claimed:
            return None
        return claimed[0] if isinstance(claimed, list) else claimed
