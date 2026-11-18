"""Queue persistence boundary for the Council worker.

The worker depends on this contract, not on a database SDK. SupabaseQueueStore
preserves the existing PostgREST/RPC behavior. PostgresQueueStore targets the
standalone schema in postgres/schema.sql and uses standard SQL row locking.
Keep Supabase as the default until API ingress and worker share one database.
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


class PostgresQueueStore:
    """Standard PostgreSQL adapter for the same Council queue contract.

    It intentionally targets the standalone schema in postgres/schema.sql rather
    than depending on Supabase RPCs, PostgREST, roles, or Edge Functions.
    """

    def __init__(self, conninfo: str, max_size: int = 12) -> None:
        if not conninfo:
            raise ValueError("DATABASE_URL is required for the PostgreSQL queue backend")
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from psycopg_pool import ConnectionPool
        self._jsonb = Jsonb

        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=1,
            max_size=max(2, min(24, int(max_size))),
            kwargs={"row_factory": dict_row},
            open=True,
        )

    def close(self) -> None:
        self._pool.close()

    def _execute_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self._pool.connection() as conn:
            return conn.execute(sql, params).fetchone()

    def load_request(self, request_id: str) -> dict[str, Any]:
        row = self._execute_one(
            "SELECT * FROM public.yj64_council_api_requests WHERE request_id = %s",
            (request_id,),
        )
        if row is None:
            raise LookupError(f"Council request not found: {request_id}")
        return row

    def is_cancelled(self, request_id: str) -> bool:
        row = self._execute_one(
            "SELECT cancel_requested, status FROM public.yj64_council_api_requests "
            "WHERE request_id = %s",
            (request_id,),
        )
        if row is None:
            return True
        return bool(row["cancel_requested"]) or row["status"] == "cancelled"

    def update_progress(self, request_id: str, worker_id: str, progress: dict[str, Any]) -> None:
        self._execute_one(
            "UPDATE public.yj64_council_api_requests "
            "SET progress = %s, updated_at = now() "
            "WHERE request_id = %s AND worker_id = %s AND status = 'running' RETURNING request_id",
            (self._jsonb(progress), request_id, worker_id),
        )

    def renew_lease(self, request_id: str, worker_id: str, lease_seconds: int) -> None:
        self._execute_one(
            "UPDATE public.yj64_council_api_requests "
            "SET lease_expires_at = now() + make_interval(secs => %s), updated_at = now() "
            "WHERE request_id = %s AND worker_id = %s AND status = 'running' RETURNING request_id",
            (lease_seconds, request_id, worker_id),
        )

    def mark_cancelled(self, request_id: str, worker_id: str) -> None:
        self._execute_one(
            "UPDATE public.yj64_council_api_requests SET status = 'cancelled', "
            "completed_at = now(), updated_at = now(), lease_expires_at = NULL "
            "WHERE request_id = %s AND worker_id = %s AND status = 'running' RETURNING request_id",
            (request_id, worker_id),
        )

    def mark_completed(self, request_id: str, worker_id: str, result: dict[str, Any]) -> None:
        self._execute_one(
            "UPDATE public.yj64_council_api_requests SET status = 'completed', result = %s, "
            "progress = %s, completed_at = now(), updated_at = now(), lease_expires_at = NULL, "
            "error_code = NULL, error_message = NULL "
            "WHERE request_id = %s AND worker_id = %s AND status = 'running' RETURNING request_id",
            (self._jsonb(result), self._jsonb({"phase": "completed"}), request_id, worker_id),
        )

    def record_event(self, request_id: str, agent_id: str, event_type: str, details: dict[str, Any]) -> None:
        self._execute_one(
            "INSERT INTO public.yj64_council_api_events "
            "(request_id, agent_id, event_type, details) VALUES (%s, %s, %s, %s) RETURNING event_id",
            (request_id, agent_id, event_type, self._jsonb(details)),
        )

    def record_attempt_failure(self, request_id: str, worker_id: str, message: str) -> None:
        self._execute_one(
            "UPDATE public.yj64_council_api_requests SET error_code = 'worker_attempt_failed', "
            "error_message = %s, lease_expires_at = now(), updated_at = now() "
            "WHERE request_id = %s AND worker_id = %s AND status = 'running' RETURNING request_id",
            (message[:2000], request_id, worker_id),
        )

    def fail_exhausted_leases(self) -> None:
        self._execute_one(
            "UPDATE public.yj64_council_api_requests SET status = 'failed', "
            "error_code = 'worker_retries_exhausted', "
            "error_message = 'Worker lease expired after the maximum number of attempts.', "
            "completed_at = now(), updated_at = now(), lease_expires_at = NULL "
            "WHERE status = 'running' AND lease_expires_at < now() "
            "AND attempts >= max_attempts RETURNING request_id"
        )

    def publish_heartbeat(self, worker_id: str, status: str, routes: list[str]) -> None:
        self._execute_one(
            "INSERT INTO public.yj64_council_api_workers "
            "(worker_id, status, version, routes, last_seen_at, updated_at) "
            "VALUES (%s, %s, 'yj64-council-worker/1.0.0', %s, now(), now()) "
            "ON CONFLICT (worker_id) DO UPDATE SET status = EXCLUDED.status, "
            "version = EXCLUDED.version, routes = EXCLUDED.routes, "
            "last_seen_at = now(), updated_at = now() RETURNING worker_id",
            (worker_id, status, routes),
        )

    def claim(self, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        return self._execute_one(
            """
            WITH candidate AS (
                SELECT request_id
                FROM public.yj64_council_api_requests
                WHERE cancel_requested = false
                  AND (
                    status = 'accepted'
                    OR (
                      status = 'running'
                      AND lease_expires_at < now()
                      AND attempts < max_attempts
                    )
                  )
                ORDER BY created_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE public.yj64_council_api_requests AS request
            SET status = 'running',
                worker_id = %s,
                lease_expires_at = now() + make_interval(secs => %s),
                attempts = request.attempts + 1,
                updated_at = now()
            FROM candidate
            WHERE request.request_id = candidate.request_id
            RETURNING request.*
            """,
            (worker_id, lease_seconds),
        )
