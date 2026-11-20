"""Durable Council queue worker (continuous or bounded one-shot mode)."""
from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import atexit
import os
import signal
import socket
import threading
import traceback
import uuid
from typing import Any

from cloud_worker.engine import CouncilCancelled, CouncilEngine, load_provider_routes
from cloud_worker.queue_store import PostgresQueueStore, QueueStore, SupabaseQueueStore

POLL_SECONDS = max(1, int(os.environ.get("YJ64_WORKER_POLL_SECONDS", "3")))
WORKER_CONCURRENCY = max(1, min(8, int(os.environ.get("YJ64_WORKER_CONCURRENCY", "2"))))
LEASE_SECONDS = max(60, min(900, int(os.environ.get("YJ64_WORKER_LEASE_SECONDS", "180"))))
WORKER_ID = os.environ.get("YJ64_WORKER_ID") or f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"

stop_event = threading.Event()
runtime_store: QueueStore | None = None
runtime_routes: list[str] = []


def build_queue_store() -> QueueStore:
    """Create the selected queue adapter from runtime configuration."""
    backend = os.environ.get("YJ64_QUEUE_BACKEND", "supabase").strip().lower()
    if backend == "supabase":
        from supabase import create_client

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for the Supabase backend")
        return SupabaseQueueStore(create_client(url, key))
    if backend == "postgres":
        conninfo = os.environ.get("DATABASE_URL", "")
        pool_size = int(os.environ.get("YJ64_DB_POOL_SIZE", "12"))
        return PostgresQueueStore(conninfo, max_size=pool_size)
    raise RuntimeError(f"Unsupported YJ64_QUEUE_BACKEND={backend!r}; use 'supabase' or 'postgres'")


def heartbeat(
    store: QueueStore, request_id: str, finished: threading.Event
) -> None:
    while not finished.wait(max(15, LEASE_SECONDS // 3)):
        try:
            if store.is_cancelled(request_id):
                return
            store.renew_lease(request_id, WORKER_ID, LEASE_SECONDS)
        except Exception:
            # Lease expiry enables another worker to recover the task.
            continue


def process(
    store: QueueStore, row: dict[str, Any], routes: dict[str, dict[str, str]]
) -> None:
    request_id = row["request_id"]
    session_id = row["session_id"]
    finished = threading.Event()
    heartbeat_thread = threading.Thread(
        target=heartbeat, args=(store, request_id, finished), daemon=True
    )
    heartbeat_thread.start()
    try:
        def report(event: dict[str, Any]) -> None:
            store.update_progress(request_id, WORKER_ID, event)
            if store.is_cancelled(request_id):
                raise CouncilCancelled("Cancellation requested")

        # One engine instance per request prevents progress callbacks/history from crossing chats.
        engine = CouncilEngine(routes=routes, report=report)
        request = {
            "mode": row["mode"],
            "task": row["task"],
            "limits": row["limits"],
            "voting": row["voting"],
        }
        result = engine.run(
            request, request_id, session_id, lambda: store.is_cancelled(request_id)
        )
        if store.is_cancelled(request_id):
            store.mark_cancelled(request_id, WORKER_ID)
            return

        store.mark_completed(request_id, WORKER_ID, result)
        store.record_event(
            request_id, row["agent_id"], "council_completed",
            {"outcome": result["outcome"]},
        )
    except CouncilCancelled:
        store.mark_cancelled(request_id, WORKER_ID)
    except Exception as exc:
        # Retry is handled by lease expiry and max_attempts in the database claim function.
        try:
            store.record_event(
                request_id, row["agent_id"], "worker_attempt_failed",
                {"error_type": type(exc).__name__, "message": str(exc)[:1000]},
            )
            store.record_attempt_failure(request_id, WORKER_ID, str(exc))
        except Exception:
            traceback.print_exc()
    finally:
        finished.set()
        heartbeat_thread.join(timeout=2)


def main() -> None:
    """Run continuously by default, or stop after YJ64_WORKER_MAX_TASKS claims.

    A value of 0 preserves the long-lived service behavior. Bounded mode is
    intended for ephemeral runners: it drains all claimed tasks before exit.
    """
    global runtime_store, runtime_routes
    stop_event.clear()
    max_tasks = max(0, int(os.environ.get("YJ64_WORKER_MAX_TASKS", "0")))
    routes = load_provider_routes()
    store = build_queue_store()
    runtime_store = store
    runtime_routes = list(routes)
    close_store = getattr(store, "close", None)
    if callable(close_store):
        atexit.register(close_store)

    claimed_count = 0
    try:
        store.publish_heartbeat(WORKER_ID, "running", list(routes))
        print(
            f"YJ-64 Council worker {WORKER_ID} ready; routes={','.join(routes)}; "
            f"concurrency={WORKER_CONCURRENCY}; max_tasks={max_tasks or 'unlimited'}",
            flush=True,
        )
        # Count claims, not completions: every claimed task consumes this run's
        # budget even if it fails and is later recovered through lease expiry.
        with ThreadPoolExecutor(max_workers=WORKER_CONCURRENCY) as executor:
            active = set()
            while active or (
                not stop_event.is_set()
                and (max_tasks == 0 or claimed_count < max_tasks)
            ):
                try:
                    store.publish_heartbeat(WORKER_ID, "running", list(routes))
                    store.fail_exhausted_leases()
                    while (
                        not stop_event.is_set()
                        and (max_tasks == 0 or claimed_count < max_tasks)
                        and len(active) < WORKER_CONCURRENCY
                    ):
                        row = store.claim(WORKER_ID, LEASE_SECONDS)
                        if row is None:
                            break
                        claimed_count += 1
                        active.add(executor.submit(process, store, row, routes))
                    if active:
                        completed, active = wait(
                            active, timeout=POLL_SECONDS, return_when=FIRST_COMPLETED
                        )
                        for future in completed:
                            try:
                                future.result()
                            except Exception as exc:
                                print(
                                    f"task execution error: {type(exc).__name__}: {str(exc)[:1000]}",
                                    flush=True,
                                )
                    elif not stop_event.is_set() and (max_tasks == 0 or claimed_count < max_tasks):
                        stop_event.wait(POLL_SECONDS)
                except Exception as exc:
                    print(
                        f"worker loop error: {type(exc).__name__}: {str(exc)[:1000]}",
                        flush=True,
                    )
                    if not active:
                        stop_event.wait(min(30, POLL_SECONDS * 3))
    finally:
        # Mark the ephemeral worker inactive even when its bounded run or loop
        # ends with an exception. In-flight task leases remain recoverable.
        stop_event.set()
        try:
            store.publish_heartbeat(WORKER_ID, "stopped", list(routes))
        except Exception as exc:
            print(
                f"could not publish stopped heartbeat: {type(exc).__name__}: {str(exc)[:500]}",
                flush=True,
            )
        runtime_store = None
        runtime_routes = []


def shutdown(_signum: int, _frame: Any) -> None:
    stop_event.set()
    if runtime_store is not None:
        try:
            runtime_store.publish_heartbeat(WORKER_ID, "stopping", runtime_routes)
        except Exception:
            pass


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    main()
