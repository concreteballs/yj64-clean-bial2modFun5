"""Durable Council queue worker. Run as a separate long-lived container."""
from __future__ import annotations

import json
import os
import signal
import socket
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import create_client
from cloud_worker.engine import CouncilCancelled, CouncilEngine, load_provider_routes

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
POLL_SECONDS = max(1, int(os.environ.get("YJ64_WORKER_POLL_SECONDS", "3")))
LEASE_SECONDS = max(60, min(900, int(os.environ.get("YJ64_WORKER_LEASE_SECONDS", "180"))))
WORKER_ID = os.environ.get("YJ64_WORKER_ID") or f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"

db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
stop_event = threading.Event()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_request(request_id: str) -> dict[str, Any]:
    response = db.table("yj64_council_api_requests").select("*").eq("request_id", request_id).single().execute()
    return response.data


def is_cancelled(request_id: str) -> bool:
    row = db.table("yj64_council_api_requests").select("cancel_requested,status").eq("request_id", request_id).single().execute().data
    return bool(row.get("cancel_requested")) or row.get("status") == "cancelled"


def update_progress(request_id: str, progress: dict[str, Any]) -> None:
    db.table("yj64_council_api_requests").update({
        "progress": progress, "updated_at": utc_now()
    }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()


def renew_lease(request_id: str) -> None:
    expires = (datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)).isoformat()
    db.table("yj64_council_api_requests").update({
        "lease_expires_at": expires, "updated_at": utc_now()
    }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()


def heartbeat(request_id: str, finished: threading.Event) -> None:
    while not finished.wait(max(15, LEASE_SECONDS // 3)):
        try:
            if is_cancelled(request_id):
                return
            renew_lease(request_id)
        except Exception:
            # Lease expiry enables another worker to recover the task.
            continue


def finish_failed(request_id: str, code: str, message: str) -> None:
    db.table("yj64_council_api_requests").update({
        "status": "failed",
        "error_code": code[:100],
        "error_message": message[:2000],
        "completed_at": utc_now(),
        "updated_at": utc_now(),
        "lease_expires_at": None,
    }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()


def process(row: dict[str, Any], engine: CouncilEngine) -> None:
    request_id = row["request_id"]
    session_id = row["session_id"]
    finished = threading.Event()
    heartbeat_thread = threading.Thread(target=heartbeat, args=(request_id, finished), daemon=True)
    heartbeat_thread.start()
    try:
        def report(event: dict[str, Any]) -> None:
            update_progress(request_id, event)
            if is_cancelled(request_id):
                raise CouncilCancelled("Cancellation requested")
        engine.report = report
        request = {
            "mode": row["mode"],
            "task": row["task"],
            "limits": row["limits"],
            "voting": row["voting"],
        }
        result = engine.run(request, request_id, session_id, lambda: is_cancelled(request_id))
        if is_cancelled(request_id):
            db.table("yj64_council_api_requests").update({
                "status": "cancelled", "completed_at": utc_now(),
                "updated_at": utc_now(), "lease_expires_at": None,
            }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()
            return
        db.table("yj64_council_api_requests").update({
            "status": "completed", "result": result, "progress": {"phase": "completed"},
            "completed_at": utc_now(), "updated_at": utc_now(), "lease_expires_at": None,
            "error_code": None, "error_message": None,
        }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()
        db.table("yj64_council_api_events").insert({
            "request_id": request_id, "agent_id": row["agent_id"],
            "event_type": "council_completed", "details": {"outcome": result["outcome"]},
        }).execute()
    except CouncilCancelled:
        db.table("yj64_council_api_requests").update({
            "status": "cancelled", "completed_at": utc_now(),
            "updated_at": utc_now(), "lease_expires_at": None,
        }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()
    except Exception as exc:
        # Retry is handled by lease expiry and max_attempts in the DB claim function.
        try:
            db.table("yj64_council_api_events").insert({
                "request_id": request_id, "agent_id": row["agent_id"],
                "event_type": "worker_attempt_failed",
                "details": {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
            }).execute()
            db.table("yj64_council_api_requests").update({
                "error_code": "worker_attempt_failed",
                "error_message": str(exc)[:2000],
                "lease_expires_at": utc_now(),
                "updated_at": utc_now(),
            }).eq("request_id", request_id).eq("worker_id", WORKER_ID).eq("status", "running").execute()
        except Exception:
            traceback.print_exc()
    finally:
        finished.set()
        heartbeat_thread.join(timeout=2)


def main() -> None:
    # Validate provider secrets before claiming work.
    routes = load_provider_routes()
    engine = CouncilEngine(routes=routes)
    print(f"YJ-64 Council worker {WORKER_ID} ready; routes={','.join(routes)}", flush=True)
    while not stop_event.is_set():
        try:
            claimed = db.rpc("yj64_claim_council_api_request", {
                "p_worker_id": WORKER_ID, "p_lease_seconds": LEASE_SECONDS,
            }).execute().data or []
            if not claimed:
                stop_event.wait(POLL_SECONDS)
                continue
            for row in claimed:
                if stop_event.is_set():
                    break
                process(row, engine)
        except Exception as exc:
            print(f"worker loop error: {type(exc).__name__}: {str(exc)[:1000]}", flush=True)
            stop_event.wait(min(30, POLL_SECONDS * 3))


def shutdown(_signum: int, _frame: Any) -> None:
    stop_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
