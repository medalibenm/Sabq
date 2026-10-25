"""Worker (service `worker`): the only process that polls sources.

Exactly one worker runs. It keeps a heartbeat file for the Docker health check and runs the
ingestion scheduler (plan M5; `INGEST_ENABLED=false` keeps only the heartbeat). Story matching is
added in M8.
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


async def heartbeat(settings: Settings, stop: asyncio.Event) -> None:
    path = Path(settings.worker_heartbeat_file)
    while not stop.is_set():
        path.touch()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=settings.worker_tick_seconds)


async def ingest(settings: Settings, stop: asyncio.Event) -> None:
    from sabq.db.session import get_sync_sessionmaker
    from sabq.fetch import Fetcher
    from sabq.ingest.poller import Database
    from sabq.ingest.scheduler import Scheduler

    async with Fetcher(settings) as fetcher:
        await Scheduler(settings, fetcher, Database(get_sync_sessionmaker())).run(stop)


async def run(settings: Settings, stop: asyncio.Event) -> None:
    log.info(
        "worker started (version %s, ingestion %s)",
        __version__,
        "on" if settings.ingest_enabled else "off",
    )
    tasks = [heartbeat(settings, stop)]
    if settings.ingest_enabled:
        tasks.append(ingest(settings, stop))
    await asyncio.gather(*tasks)
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
