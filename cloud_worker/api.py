"""Portable YJ-64 Council HTTP ingress.

Implements the public contract of supabase/functions/council-api using
standard PostgreSQL only. Put this service behind an HTTPS reverse proxy.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

VERSION = "yj64.council-api.v1"
MAX_BODY_BYTES = 128 * 1024
PRIVATE_FIELD = re.compile(r"^(individual_votes|ballots|private_ratings|competence_scores)$", re.I)
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
REQUEST_PATH = "/api/v1/external-agents/council/requests"

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                dsn = os.environ.get("DATABASE_URL", "").strip()
                if not dsn:
                    raise RuntimeError("DATABASE_URL is required")
                _pool = ConnectionPool(
                    conninfo=dsn, min_size=1,
                    max_size=max(2, min(24, int(os.environ.get("YJ64_API_DB_POOL_SIZE", "8")))),
                    kwargs={"row_factory": dict_row}, open=True,
                )
    return _pool


def db_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with pool().connection() as conn:
        return conn.execute(sql, params).fetchone()


def db_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        return list(conn.execute(sql, params).fetchall())


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def has_private_fields(value: Any, depth: int = 0) -> bool:
    if depth > 16:
        return True
    if isinstance(value, list):
        return any(has_private_fields(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return any(PRIVATE_FIELD.match(str(key)) or has_private_fields(item, depth + 1)
                   for key, item in value.items())
    return False


def validate_request(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "body_must_be_object"
    allowed = {"protocol_version", "agent_id", "correlation_id", "idempotency_key", "mode", "task", "limits", "voting"}
    if set(value) - allowed:
        return "unknown_request_field"
    if value.get("protocol_version") != VERSION:
        return "invalid_protocol_version"
    if not ID_PATTERN.fullmatch(str(value.get("agent_id", ""))) or not ID_PATTERN.fullmatch(str(value.get("correlation_id", ""))):
        return "invalid_identifier"
    idem = value.get("idempotency_key")
    if not isinstance(idem, str) or not 8 <= len(idem) <= 256:
        return "invalid_idempotency_key"
    if value.get("mode") not in ("consensus", "critique"):
        return "invalid_mode"
    task = value.get("task")
    if not isinstance(task, dict):
        return "invalid_task"
    if set(task) - {"title", "prompt", "context", "evidence_refs"}:
        return "unknown_task_field"
    if not isinstance(task.get("title"), str) or not 1 <= len(task["title"]) <= 500:
        return "invalid_task_title"
    if not isinstance(task.get("prompt"), str) or not 1 <= len(task["prompt"]) <= 50000:
        return "invalid_task_prompt"
    if not isinstance(task.get("context"), dict):
        return "invalid_task_context"
    refs = task.get("evidence_refs")
    if not isinstance(refs, list) or len(refs) > 100 or any(not isinstance(x, str) or not 1 <= len(x) <= 2048 for x in refs):
        return "invalid_evidence_refs"
    limits = value.get("limits")
    if not isinstance(limits, dict):
        return "invalid_limits"
    if set(limits) - {"max_rounds", "timeout_seconds", "max_output_tokens", "minimum_critique_rounds", "allow_early_stop"}:
        return "unknown_limits_field"
    for key, low, high, error in (
        ("max_rounds", 1, 10, "invalid_max_rounds"),
        ("timeout_seconds", 30, 86400, "invalid_timeout_seconds"),
        ("max_output_tokens", 256, 100000, "invalid_max_output_tokens"),
    ):
        number = limits.get(key)
        if isinstance(number, bool) or not isinstance(number, int) or not low <= number <= high:
            return error
    if isinstance(limits.get("minimum_critique_rounds"), bool) or limits.get("minimum_critique_rounds") != 1 or not isinstance(limits.get("allow_early_stop"), bool):
        return "invalid_critique_limits"
    voting = value.get("voting")
    if not isinstance(voting, dict) or set(voting) - {"enabled", "weighted"}:
        return "invalid_voting"
    if not isinstance(voting.get("enabled"), bool) or not isinstance(voting.get("weighted"), bool):
        return "invalid_voting"
    return None


def status_payload(row: dict[str, Any]) -> dict[str, Any]:
    result = {
        "protocol_version": VERSION,
        "request_id": str(row["request_id"]),
        "session_id": str(row["session_id"]),
        "status": row["status"],
        "updated_at": row["updated_at"].isoformat(),
    }
    if row.get("progress"):
        result["progress"] = row["progress"]
    return result


def error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status, headers={"cache-control": "no-store"})


async def read_limited_body(request: Request, limit: int) -> bytes | None:
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > limit:
                return None
        except ValueError:
            return None
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def authenticate(request: Request, scope: str) -> dict[str, Any] | JSONResponse:
    auth = request.headers.get("authorization", "")
    match = re.fullmatch(r"Bearer ([^\s]{16,4096})", auth)
    if not match:
        return error("unauthorized", 401)
    row = db_one(
        "SELECT agent_id, scopes, enabled FROM public.yj64_council_api_agents "
        "WHERE token_hash = %s AND enabled = true",
        (sha256(match.group(1)),),
    )
    if not row or not isinstance(row["scopes"], list) or scope not in row["scopes"]:
        return error("unauthorized_or_scope_missing", 401)
    db_one(
        "UPDATE public.yj64_council_api_agents SET last_used_at = now() "
        "WHERE agent_id = %s RETURNING agent_id", (row["agent_id"],)
    )
    return row


def record_event(request_id: str, agent_id: str, event_type: str, details: dict[str, Any] | None = None) -> None:
    db_one(
        "INSERT INTO public.yj64_council_api_events(request_id, agent_id, event_type, details) "
        "VALUES (%s, %s, %s, %s) RETURNING event_id",
        (request_id, agent_id, event_type, Jsonb(details or {})),
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


app = FastAPI(title="YJ-64 Council API", version=VERSION, docs_url=None, redoc_url=None, lifespan=lifespan)


@app.middleware("http")
async def disable_response_caching(request: Request, call_next):
    response = await call_next(request)
    response.headers["cache-control"] = "no-store"
    response.headers["x-content-type-options"] = "nosniff"
    return response


@app.get("/health")
def health():
    try:
        db_one("SELECT 1 AS ok")
        workers = db_all(
            "SELECT worker_id, routes, last_seen_at FROM public.yj64_council_api_workers "
            "WHERE status = 'running' AND last_seen_at > now() - interval '120 seconds' "
            "ORDER BY last_seen_at DESC LIMIT 5"
        )
    except Exception:
        return JSONResponse({
            "status": "degraded", "api": "up", "database": "unavailable",
            "council_engine": "not_connected", "worker": "unknown", "ready_for_requests": False,
        }, status_code=503)
    worker_ready = bool(workers)
    adapter_ready = os.environ.get("YJ64_COUNCIL_ENGINE_ADAPTER") == "ready"
    enabled = os.environ.get("YJ64_COUNCIL_WORKER_ENABLED") == "true"
    return {
        "status": "ok", "api": "up", "database": "up",
        "council_engine": "configured" if adapter_ready else "not_connected",
        "worker": "running" if worker_ready else "not_deployed",
        "active_workers": len(workers),
        "ready_for_requests": worker_ready and adapter_ready and enabled,
    }


@app.post(REQUEST_PATH)
async def submit(request: Request):
    if request.headers.get("x-yj64-protocol-version") != VERSION:
        return error("unsupported_protocol_version", 400)
    if os.environ.get("YJ64_COUNCIL_WORKER_ENABLED") != "true" or os.environ.get("YJ64_COUNCIL_ENGINE_ADAPTER") != "ready":
        return JSONResponse({
            "error": "council_engine_not_ready",
            "message": "Request intake is disabled until the real Council worker and server-side engine adapter are deployed.",
        }, status_code=503)
    try:
        live = db_one(
            "SELECT worker_id FROM public.yj64_council_api_workers "
            "WHERE status = 'running' AND last_seen_at > now() - interval '120 seconds' LIMIT 1"
        )
    except Exception:
        return error("database_unavailable", 503)
    if not live:
        return JSONResponse({"error": "council_worker_unavailable", "message": "No live Council worker heartbeat is available."}, status_code=503)
    agent = authenticate(request, "council:submit")
    if isinstance(agent, JSONResponse):
        return agent
    try:
        raw = await read_limited_body(request, MAX_BODY_BYTES)
    except Exception:
        return error("invalid_json", 400)
    if raw is None:
        return error("payload_too_large", 413)
    try:
        body = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeDecodeError):
        return error("invalid_json", 400)
    validation = validate_request(body)
    if validation:
        return JSONResponse({"error": "invalid_request", "message": validation}, status_code=400)
    if len(stable(body).encode("utf-8")) > MAX_BODY_BYTES:
        return error("payload_too_large", 413)
    if body["agent_id"] != agent["agent_id"]:
        return error("agent_identity_mismatch", 403)
    if request.headers.get("idempotency-key") != body["idempotency_key"]:
        return error("idempotency_header_mismatch", 400)
    try:
        request_hash = sha256(stable(body))
    except (TypeError, ValueError):
        return error("invalid_json", 400)
    existing = db_one(
        "SELECT request_id, session_id, request_hash, status FROM public.yj64_council_api_requests "
        "WHERE agent_id = %s AND idempotency_key = %s",
        (agent["agent_id"], body["idempotency_key"]),
    )
    if existing:
        if existing["request_hash"] != request_hash:
            return error("idempotency_conflict", 409)
        if existing["status"] not in ("accepted", "running"):
            return JSONResponse({"error": "idempotency_replay_terminal", "request_id": str(existing["request_id"]), "status": existing["status"]}, status_code=409)
        return JSONResponse({
            "protocol_version": VERSION, "request_id": str(existing["request_id"]),
            "session_id": str(existing["session_id"]), "status": existing["status"],
        }, status_code=202)
    try:
        row = db_one(
            """
            INSERT INTO public.yj64_council_api_requests
                (agent_id, correlation_id, idempotency_key, request_hash,
                 protocol_version, mode, task, limits, voting, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'accepted')
            ON CONFLICT (agent_id, idempotency_key) DO NOTHING
            RETURNING request_id, session_id, status
            """,
            (agent["agent_id"], body["correlation_id"], body["idempotency_key"], request_hash,
             VERSION, body["mode"], Jsonb(body["task"]), Jsonb(body["limits"]), Jsonb(body["voting"])),
        )
    except Exception:
        return error("request_persistence_failed", 503)
    if not row:
        return error("idempotency_race_retry", 409)
    record_event(str(row["request_id"]), agent["agent_id"], "request_accepted",
                 {"correlation_id": body["correlation_id"], "mode": body["mode"]})
    return JSONResponse({
        "protocol_version": VERSION, "request_id": str(row["request_id"]),
        "session_id": str(row["session_id"]), "status": "accepted",
    }, status_code=202)


def parse_request_id(value: str) -> bool:
    try:
        UUID(value)
        return bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value, re.I))
    except (ValueError, TypeError):
        return False


def get_owned_request(request_id: str, agent_id: str) -> dict[str, Any] | None:
    return db_one(
        "SELECT * FROM public.yj64_council_api_requests WHERE request_id = %s AND agent_id = %s",
        (request_id, agent_id),
    )


@app.get(REQUEST_PATH + "/{request_id}")
def get_status(request_id: str, request: Request):
    if not parse_request_id(request_id):
        return error("invalid_request_id", 400)
    if request.headers.get("x-yj64-protocol-version") != VERSION:
        return error("unsupported_protocol_version", 400)
    agent = authenticate(request, "council:read")
    if isinstance(agent, JSONResponse):
        return agent
    row = get_owned_request(request_id, agent["agent_id"])
    if not row:
        return error("not_found", 404)
    return status_payload(row)


@app.get(REQUEST_PATH + "/{request_id}/result")
def get_result(request_id: str, request: Request):
    if not parse_request_id(request_id):
        return error("invalid_request_id", 400)
    if request.headers.get("x-yj64-protocol-version") != VERSION:
        return error("unsupported_protocol_version", 400)
    agent = authenticate(request, "council:read")
    if isinstance(agent, JSONResponse):
        return agent
    row = get_owned_request(request_id, agent["agent_id"])
    if not row:
        return error("not_found", 404)
    if row["status"] == "completed" and row.get("result"):
        result = row["result"]
        required = ("claims", "participant_positions", "dissent", "evidence", "unresolved_questions")
        valid = (
            isinstance(result, dict)
            and result.get("protocol_version") == VERSION
            and str(result.get("request_id")) == str(row["request_id"])
            and str(result.get("session_id")) == str(row["session_id"])
            and result.get("status") == "completed"
            and result.get("outcome") in ("consensus", "qualified_consensus", "unresolved_disagreement", "insufficient_evidence")
            and isinstance(result.get("summary"), str) and 0 < len(result["summary"]) <= 50000
            and all(isinstance(result.get(key), list) for key in required)
            and not has_private_fields(result)
        )
        if not valid:
            return error("stored_council_result_failed_validation", 500)
        return result
    if row["status"] in ("blocked", "failed", "cancelled"):
        return JSONResponse({"error": row["status"], "message": row.get("error_message") or "Council request ended without a result"}, status_code=409)
    return JSONResponse(status_payload(row), status_code=202)


@app.post(REQUEST_PATH + "/{request_id}/cancel")
async def cancel(request_id: str, request: Request):
    if not parse_request_id(request_id):
        return error("invalid_request_id", 400)
    if request.headers.get("x-yj64-protocol-version") != VERSION:
        return error("unsupported_protocol_version", 400)
    agent = authenticate(request, "council:cancel")
    if isinstance(agent, JSONResponse):
        return agent
    try:
        raw = await read_limited_body(request, 4096)
        if raw is None:
            return error("payload_too_large", 413)
        body = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeDecodeError):
        return error("invalid_json", 400)
    if not isinstance(body, dict) or body.get("protocol_version") != VERSION or body.get("agent_id") != agent["agent_id"] or set(body) - {"protocol_version", "agent_id"}:
        return error("invalid_cancel_request", 400)
    current = db_one(
        "SELECT request_id, status FROM public.yj64_council_api_requests "
        "WHERE request_id = %s AND agent_id = %s",
        (request_id, agent["agent_id"]),
    )
    if not current:
        return error("not_found", 404)
    if current["status"] in ("completed", "blocked", "failed", "cancelled"):
        return {"protocol_version": VERSION, "request_id": request_id, "status": current["status"]}
    updated = db_one(
        """
        UPDATE public.yj64_council_api_requests
        SET status = 'cancelled', cancel_requested = true,
            completed_at = now(), updated_at = now(), lease_expires_at = NULL
        WHERE request_id = %s AND agent_id = %s AND status IN ('accepted', 'running')
        RETURNING status
        """,
        (request_id, agent["agent_id"]),
    )
    if updated:
        record_event(request_id, agent["agent_id"], "request_cancelled", {})
        return {"protocol_version": VERSION, "request_id": request_id, "status": "cancelled"}
    after = db_one(
        "SELECT status FROM public.yj64_council_api_requests WHERE request_id = %s AND agent_id = %s",
        (request_id, agent["agent_id"]),
    )
    if not after or after["status"] not in ("completed", "blocked", "failed", "cancelled"):
        return error("cancel_state_race_retry", 409)
    return {"protocol_version": VERSION, "request_id": request_id, "status": after["status"]}
