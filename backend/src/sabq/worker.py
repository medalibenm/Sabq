"""Worker (service `worker`): the only process that polls sources.

Exactly one worker runs. In M1 it only keeps a heartbeat for the Docker health check; the
scheduler, polling and story matching are added in later milestones (docs/plan.md).
Run: python -m sabq.worker
"""

import asyncio
import contextlib
import logging
import signal
from pathlib import Path

from sabq import __version__
from sabq.logs import configure_logging
from sabq.settings import Settings, get_settings

log = logging.getLogger("sabq.worker")


async def run(settings: Settings, stop: asyncio.Event) -> None:
    heartbeat = Path(settings.worker_heartbeat_file)
    log.info("worker started (version %s)", __version__)
    while not stop.is_set():
        heartbeat.touch()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_tick_seconds)
    log.info("worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    async def _main() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:  # Windows development shell
                signal.signal(sig, lambda *_: stop.set())
        await run(settings, stop)

    asyncio.run(_main())


if __name__ == "__main__":
    main()
