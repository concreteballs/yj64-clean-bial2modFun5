"""Bounded GitHub Actions wrapper for the existing durable Council worker."""
from __future__ import annotations

import os
import threading

from cloud_worker import worker


def main() -> None:
    max_runtime = max(300, min(20_400, int(os.environ.get(
        "YJ64_ACTIONS_MAX_RUNTIME_SECONDS", "20400"
    ))))
    timer = threading.Timer(max_runtime, worker.shutdown, args=(0, None))
    timer.daemon = True
    timer.start()
    try:
        worker.main()
    finally:
        timer.cancel()


if __name__ == "__main__":
    main()
