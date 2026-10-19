import asyncio
import os
import sys

import pytest

if sys.platform == "win32":  # psycopg's async driver needs a selector loop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def pytest_collection_modifyitems(config, items):
    """Database tests run only when DATABASE_URL is set (CI, or `docker compose` locally)."""
    if os.environ.get("DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="DATABASE_URL not set")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)
