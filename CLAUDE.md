# CLAUDE.md

Guidance for Claude Code working in this repository.

## Project
Sabq (سبق) is a news radar for newsrooms: it turns news and official sites (many without RSS) into feeds and alerts. Read `README.md` first, then the doc relevant to the task in `docs/`.

## Current phase
Build (started 2026-10-19): source investigation and backend, following `docs/plan.md` step by step; tick items and update its status table as work completes. Docs in `docs/` are the source of truth; keep them updated when a decision changes. Record every product or architecture decision in `docs/decisions.md` with its date.

## Rules that apply to all work
- **robots.txt is checked live before any investigation or fetching.** If it disallows us, stop: mark the source `blocked_by_robots` and explain why. Never suggest or implement ways around robots.txt, bot protection, logins or paywalls.
- **No third-party scraping services** (Apify, ScrapingBee, Bright Data, RSS.app, FetchRSS…) unless `docs/decisions.md` records an approved exception.
- **Structured data first:** RSS/Atom → platform APIs → sitemaps → embedded page data → the site's own internal API → CSS selectors (last resort). See `docs/architecture.md`.
- **Public outputs never contain full article text.** Title, lead, image, link only.
- **Dates are stored in UTC** with a confidence level; naive dates from Algerian sites are `Africa/Algiers`.
- **Arabic text is stored as-is** (NFC normalised), never transliterated.
- Identify as our own bot User-Agent (`SabqBot/<version> (+contact URL)`).
- **Build for the deployment target:** one EU server (DigitalOcean or Hetzner) with Docker Compose
  (`db`, `app`, `worker`, `proxy`). Everything runs via `docker compose up`, config from env vars,
  no secrets committed, memory budget respected, nothing provider-specific in code. Follow `docs/architecture.md#deployment`.

## Adding a source
Follow `docs/adding-sources.md` step by step. Record the result in `docs/sources.md` (method, interval, robots status, date verified) and save sample responses as test fixtures.

## Planned stack (not yet built)
Python 3.12, FastAPI, httpx, PostgreSQL 16 + pgvector (SQLAlchemy 2 + Alembic), feedgen, trafilatura, dateparser, pydantic; Voyage AI `voyage-4` embeddings via OpenRouter for story matching; `uv`, `ruff`, `pytest`; Docker Compose on one EU server (DigitalOcean or Hetzner). Playwright only for investigation. Details in `docs/architecture.md`.
