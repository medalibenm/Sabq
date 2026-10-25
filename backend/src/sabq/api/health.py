"""Health (plan M7; decisions 2026-10-19 and 2026-10-25).

GET /health.json           public: service status and counts only (Docker and uptime checks);
                           503 only when the database is down, never because of a source
GET /health                Sabq team: per-source page, problems first (HTML)
GET /health/sources.json   Sabq team: the same as JSON
"""

import html
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text

from sabq import __version__
from sabq.api.deps import DB, Viewer, platform_admin
from sabq.db.models import FetchRun, Source
from sabq.db.session import get_engine
from sabq.health import SourceHealth, human, source_health

router = APIRouter(tags=["health"])
TeamMember = Annotated[Viewer, Depends(platform_admin)]


class SourceHealthOut(BaseModel):
    slug: str
    name: str
    enabled: bool
    status: str
    status_since: datetime | None
    needs_attention: bool
    warnings: list[str]
    access_method: str
    poll_interval_s: int
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None
    failures_in_a_row: int
    new_last_24h: int
    median_delay_s: float | None
    last_new_at: datetime | None
    usual_quiet_s: float | None
    last_items_seen: int | None
    usual_items_seen: float | None


def out(health: SourceHealth) -> SourceHealthOut:
    return SourceHealthOut(**vars(health), needs_attention=health.needs_attention)


@router.get("/health.json")
async def health(response: Response) -> dict:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            statuses = dict(
                (
                    await conn.execute(
                        select(Source.status, func.count())
                        .where(Source.enabled.is_(True))
                        .group_by(Source.status)
                    )
                ).all()
            )
            last_poll = await conn.scalar(select(func.max(FetchRun.started_at)))
        database = "ok"
    except Exception:
        database, statuses, last_poll = "unavailable", {}, None
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if database == "ok" else "degraded",
        "version": __version__,
        "database": database,
        "sources": statuses,
        "last_poll_at": last_poll.isoformat() if last_poll else None,
    }


@router.get("/health/sources.json")
async def sources_health(viewer: TeamMember, db: DB) -> list[SourceHealthOut]:
    return [out(h) for h in await source_health(db, datetime.now(UTC))]


@router.get("/health", response_class=HTMLResponse)
async def health_page(viewer: TeamMember, db: DB) -> HTMLResponse:
    now = datetime.now(UTC)
    return HTMLResponse(render(await source_health(db, now), now))


def _ago(moment: datetime | None, now: datetime) -> str:
    return f"{human((now - moment).total_seconds())} ago" if moment else "never"


def render(rows: list[SourceHealth], now: datetime) -> str:
    def cell(value) -> str:
        return f"<td>{html.escape(str(value))}</td>"

    lines = []
    for h in rows:
        delay = human(h.median_delay_s) if h.median_delay_s is not None else "-"
        quiet = human(h.usual_quiet_s) if h.usual_quiet_s else "learning"
        problem = "problem" if h.needs_attention else ("off" if not h.enabled else "")
        lines.append(
            f'<tr class="{problem}">'
            + cell(h.slug)
            + cell(
                f"{h.status} for {_ago(h.status_since, now).removesuffix(' ago')}"
                if h.status_since
                else h.status
            )
            + cell("; ".join(h.warnings) or "-")
            + cell(_ago(h.last_success_at, now))
            + cell(h.last_error or "-" if h.failures_in_a_row else "-")
            + cell(h.new_last_24h)
            + cell(delay)
            + cell(quiet)
            + cell(f"{h.access_method}, every {human(h.poll_interval_s)}")
            + "</tr>"
        )
    attention = sum(h.needs_attention for h in rows)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sabq · source health</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font: 14px system-ui, sans-serif; margin: 1.5rem; color: #1c1c1c; background: #fff; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: start; padding: .4rem .6rem; border-bottom: 1px solid #ddd;
          vertical-align: top; }}
tr.problem td {{ background: #fdecea; }}
tr.off td {{ color: #888; }}
</style></head><body>
<h1>Source health</h1>
<p>{attention} source(s) need attention · {len(rows)} sources · {now:%Y-%m-%d %H:%M} UTC ·
version {__version__}</p>
<table><thead><tr><th>Source</th><th>Status</th><th>Warnings</th><th>Last success</th>
<th>Last error</th><th>New (24 h)</th><th>Median delay (7 d)</th><th>Usual quiet</th>
<th>Method</th></tr></thead><tbody>
{"".join(lines)}
</tbody></table></body></html>
"""
