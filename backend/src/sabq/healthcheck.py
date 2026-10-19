"""Docker health checks without curl in the image.

python -m sabq.healthcheck app      -> GET http://localhost:8000/health.json is 200
python -m sabq.healthcheck worker   -> heartbeat file touched recently
"""

import sys
import time
import urllib.request
from pathlib import Path

from sabq.settings import get_settings


def check_app() -> bool:
    try:
        with urllib.request.urlopen("http://localhost:8000/health.json", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_worker() -> bool:
    settings = get_settings()
    path = Path(settings.worker_heartbeat_file)
    max_age = max(60.0, settings.worker_tick_seconds * 6)
    return path.exists() and time.time() - path.stat().st_mtime < max_age


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "app"
    ok = check_worker() if target == "worker" else check_app()
    sys.exit(0 if ok else 1)
