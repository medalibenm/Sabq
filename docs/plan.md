# Build plan and SOP

> Started 2026-10-19. Two tracks run in parallel: **A. source investigation** and **B. backend
> build**. This file is the working checklist: tick items, update statuses, and record every
> decision in [decisions.md](decisions.md). The specs in `docs/` stay the source of truth; if the
> build shows a spec is wrong, fix the spec first, then the code.

## How we work (applies to both tracks)
1. **One step at a time:** pick the next unticked item, do it, verify it, tick it.
2. **Done means verified:** tests pass offline (`uv run pytest`), `uv run ruff check` is clean,
   and `docker compose up` still works. No item is ticked on "should work".
3. **Docs follow decisions:** a changed decision updates its doc and `decisions.md` (dated) in
   the same commit.
4. **Commits:** small, one item or sub-step per commit, message says what and why. Work on a
   branch per milestone, merge to `main` when its "done when" holds.
5. **Rules from [CLAUDE.md](../CLAUDE.md) always apply:** live robots.txt check, no third-party
   scraping services, lead-only public outputs, UTC dates, Arabic stored as-is, our User-Agent,
   build for the Docker Compose deployment.
6. **Secrets** (`OPENROUTER_API_KEY`, database password, proxy URL) only in `.env`, never in the
   repo or the chat.

## Step 0 · Repository setup (before both tracks)
- [x] `git init` in `Sabq/` (it currently sits inside the home-folder repo), `main` branch,
      `.gitignore` (`.env`, `.venv/`, `__pycache__/`, `data/`).
- [x] First commit: README, CLAUDE.md, docs.
- [x] GitHub repository (`medalibenm/Sabq`), pushed.
- [x] Bot contact URL: none for now. User-Agent is `SabqBot/<version>`, plus
      ` (+<SABQBOT_CONTACT_URL>)` when that setting is filled; it must be filled before production (M9).

## Track A · Source investigation
SOP per source: follow [adding-sources.md](adding-sources.md) exactly. Summary:

1. **robots.txt live** for our User-Agent (and for any API host found later). Disallowed →
   status `blocked_by_robots`, record why, stop.
2. **Terms / notices:** an explicit ban on automated collection → `refused`, stop.
3. **Reachability** with our User-Agent; note status and size. Blocked from abroad → note
   `egress: dz_proxy` candidate (re-test from the EU server in Track B, M9).
4. **Find the data**, in order: RSS/Atom → platform API (e.g. `/wp-json/wp/v2/posts`) →
   sitemaps → embedded page data → the site's internal API → CSS selectors (last resort).
5. **Confirm language(s):** one catalog source per language (`slug-ar`, `slug-fr`).
6. **Map fields:** ID, title, date + timezone, lead, image, section, link/image templates.
7. **Draft the config** (YAML, the format in [architecture.md](architecture.md#layer-2-config-driven-extraction))
   and save **fixtures**: two listing responses taken a few minutes apart, plus one article page.
8. **Validate** with the checks in [architecture.md](architecture.md#validating-a-config).
9. **Record** in [sources.md](sources.md): move the row to *Verified* (or *Refused*) with slug,
   wilaya, method, endpoint, proposed poll interval and tier, robots status, date, notes.

Until Track B M4 exists, configs and fixtures are drafted under `catalog/` and
`tests/fixtures/<slug>/` and checked with a small script; after M4 they are validated by the real
extractor.

**Order:** one wilaya at a time, in the order below (about 2–4 sources per session).

| # | Wilaya | Source | URL | Robots | Method | Status |
|---|---|---|---|---|---|---|
| 1 | 05 باتنة | Awras News | https://elauresnews.dz/ | allowed | WP API | verified 2026-10-19 |
| 2 | 05 باتنة | El Hidhab News | https://elhidhab.dz/ | allowed (empty) | WP API | verified 2026-10-19 |
| 3 | 15 تيزي وزو | La Dépêche de Kabylie | https://www.depechedekabylie.com | | | todo |
| 4 | 17 الجلفة | Djelfa Info | https://djelfainfo.dz/ar/ | | | todo |
| 5 | 19 سطيف | Sawt Setif | https://sawtsetif.dz/ | | | todo |
| 6 | 19 سطيف | Setif One | https://setifone.dz/ | | | todo |
| 7 | 23 عنابة | Le Provincial | https://leprovincial.dz/ | | | todo |
| 8 | 23 عنابة | Seybouse Times | https://seybousetimes.dz/ | | | todo |
| 9 | 25 قسنطينة | An-Nasr | https://www.annasronline.com/ | | | todo |
| 10 | 25 قسنطينة | Le Quotidien de Constantine | https://lequotidien-deconstantine.dz/ | | | todo |
| 11 | 27 مستغانم | La Réflexion | https://www.reflexion.dz/ | | | todo |
| 12 | 31 وهران | El Djoumhouria | https://eldjoumhouria.dz/ | | | todo |
| 13 | 31 وهران | Le Quotidien d'Oran | https://lequotidien-oran.dz/ | | | todo |
| 14 | 31 وهران | Asdaa Algharb | https://asdaalgharb.dz/ | | | todo |
| 15 | 31 وهران | L'Echo d'Oran | https://www.echodoran.com/ | | | todo |
| 16 | 42 تيبازة | Cherchell News | https://www.cherchellnews.dz/ | | | todo |
| 17 | 00 National | El Chark El Youm | https://elcharkelyoum.dz/ | | | todo |

Statuses: `todo` · `investigating` · `verified` · `blocked_by_robots` · `refused` ·
`unreachable` · `empty`.

**Track A is done when** every row has a final status, each verified source has a config,
fixtures and a row in *Verified* in `sources.md`.

## Track B · Backend build
Order follows [product.md](product.md) (access boundaries first). Each milestone lists what it
delivers and when it is done.

### M1 · Foundation
- [x] `uv` project (Python 3.12, `ruff`, `pytest`) in `backend/`; repository layout (one backend
      package with two entry points, split by domain; decision 2026-10-19):
      ```
      compose.yaml / compose.override.yaml / .env.example
      backend/
        Dockerfile, pyproject.toml, uv.lock, alembic.ini, alembic/
        src/sabq/
          settings.py, logs.py, healthcheck.py
          db/          # models, session                     (M1, tables in M2)
          api/         # FastAPI routes, thin                (M1 health)
          fetch/       # polite HTTP, robots, limits, egress (M3)
          extract/     # config schema, extractors           (M4)
          ingest/      # scheduler, new/known, wilayas       (M5)
          auth/        # users, invites, sessions, email     (M6)
          matching/    # normalize, embeddings, clusters     (M8)
          app.py       # service `app`
          worker.py    # service `worker`
        tests/fixtures/<slug>/
      catalog/         # one YAML per source (M4)
      deploy/          # Caddyfile, backup script, server notes
      frontend/        # later
      docs/
      ```
      Domain folders are created by the milestone that needs them.
- [x] One Dockerfile (non-root user, UTC), `compose.yaml` (`db` = `pgvector/pgvector:pg16`,
      one-off `migrate`, `app`, `worker`, `proxy` = Caddy), `compose.override.yaml` for
      development (code reload, Mailpit, host ports `SABQ_DB_PORT` 5440 / `SABQ_APP_PORT` 8010),
      health checks, log rotation, graceful worker stop.
- [x] `.env.example` with every setting; `GET /health.json` returns ok (checks the database).
- [x] First migration enables pgvector; tests for settings, JSON logs, worker stop, health and
      migrations up/down.
- [x] GitHub Actions: ruff, format check, pytest with a pgvector service, and a job that starts
      the production stack and waits until healthy.

**Done when** `docker compose up` on a clean machine starts all four services healthy and CI is
green.

### M2 · Data model and access boundaries
- [x] Alembic migrations for every table in [architecture.md](architecture.md#data-model-multi-tenant-and-wilaya-aware)
      (`0002`: 21 tables; choices stored as text + one CHECK each; pgvector HNSW index;
      `detection_delay_s` computed column). `alembic check` shows no drift.
- [x] Seed (`0003`): 69 wilayas + `00` National; 59–69 with `active_from = 2027-01-01`, codes and
      Arabic/French names from Journal officiel n° 50 of 15 July 2026 (checked in the PDF).
- [x] `catalog/` loader (`sabq.catalog`, `python -m sabq.cli catalog load`): YAML → `sources` +
      `source_config_versions` (new version only when the config changes) + `source_wilayas`
      (default `00`). Catalog copied into the image (`/srv/catalog`).
- [x] Access filter `sabq.access.visible_articles(organisation_id)`: active organisation ∩ enabled
      source ∩ enabled wilaya. Isolation tests; a mutation check (wilaya rule removed) makes them
      fail as expected.
- [x] Admin CLI `python -m sabq.cli`: `org create|show|wilaya|source`, `user create`,
      `catalog load`; every change audited (`audit_events.actor = cli:<os user>`).

**Done when** migrations run up and down, seeds load, and the access tests pass.

### M3 · Polite fetching
Note: Starlette 1.9 deprecates `httpx` in favour of `httpx2` (Pydantic's successor, already used
for tests). Choose `httpx2` for the fetch client unless it lacks something we need (HTTP/2,
proxies); record the choice in `decisions.md`.

- [ ] Async HTTP client: our User-Agent, 15 s timeout, HTTP/2, `ETag` / `If-Modified-Since`.
- [ ] Live robots.txt check, cached 24 h, per host (including API hosts); disallowed → source
      `blocked_by_robots`, no request sent.
- [ ] One request at a time per host, minimum gap per host, `Crawl-delay` honoured, ±20 % jitter.
- [ ] Backoff on 429/5xx and `Retry-After`; per-source `egress: dz_proxy`.

**Done when** tests with a mock server prove each rule (robots block, per-host spacing,
conditional requests, backoff).

### M4 · Config-driven extraction
- [ ] Pydantic config schema (feed / json / html), URL templates, value maps, ID and date rules,
      multiple listings merged by ID; canonical URL normalizer (`canonical_url_key`).
- [ ] Port the 4 verified sources (`aps-ar`, `mouradia-ar`, `elhayat-ar`, `aa-ar`) from the PoC
      (`C:\Users\alilo\OneDrive\Documents\PoC RSS\rss_poc\sources`, fixtures in its `tests/`)
      into `catalog/` configs, removing site-specific code where config can express it.
- [ ] Validation command implementing [Validating a config](architecture.md#validating-a-config).
- [ ] Track A configs validated here as they arrive.

**Done when** each catalog source extracts correctly from its fixtures (titles, dates in UTC,
links, images, IDs stable across two fixtures).

### M5 · Ingestion and scheduling
- [ ] Worker scheduler: per-source interval and tier, jitter, single worker.
- [ ] New vs known articles, article page fetch (`og:`, JSON-LD, trafilatura), versions on
      `content_hash` change, dates with confidence, NFC Arabic.
- [ ] Wilaya assignment by source (`article_wilayas`, method `source`).
- [ ] `fetch_runs` recorded; detection delay stored.

**Done when** the worker runs against fixtures (and then live, locally) for an hour with no
duplicates and correct wilayas.

### M6 · Login and web app API
- [ ] Login: email + password, invites (Sabq admin or organisation owner/admin), password
      reset by email, Argon2id, session cookie, rate limiting, audit events.
- [ ] Email sending via MailerSend SMTP (settings in `.env`); Mailpit in development.
- [ ] Web app API (`/app/...`): article stream with filters, article detail, my sources and
      wilayas, source requests; lead only, never `body_text`.
- [ ] Internal `GET /api/articles` and admin-only per-source RSS (`/admin/feeds/...`) for checks.

**Done when** the access tests from M2 also pass through the HTTP layer (a user never sees
another organisation's or a non-granted wilaya's articles) and the API is documented (OpenAPI)
for the frontend.

### M7 · Health and breakage
- [ ] `/health` and `/health.json` per source; silence warning; breakage rules from
      [architecture.md](architecture.md#breakage-detection); `empty` vs `broken`.
- [ ] No push alerts (decision 2026-10-19): broken, silent and blocked sources are listed first
      on `/health`, with how long they have been in that state.

**Done when** fixtures of a broken site and an empty site trigger the right status.

### M8 · Story matching
- [ ] Normalization (ar, fr), signals (numbers, places, entities), embedding client
      (OpenRouter `voyageai/voyage-4`, batched, retries, `embedding_status`).
- [ ] Candidate search (pgvector HNSW, ±36 h, other sources), scoring, conflict checks, clusters
      (average of best two, open window, no automatic cluster merges), `dedup_candidates`.
- [ ] Calibration check on real articles (noise floor, lookalikes, copies); confirm or raise the 0.90
      threshold.

**Done when** matching runs on live articles, the calibration is recorded in `decisions.md`, and
the lookalike pairs found stay apart (kept as regression fixtures).

### M9 · Deployment
- [ ] Fill `SABQBOT_CONTACT_URL` (page explaining the bot, contact address).
- [ ] Provision a DigitalOcean droplet (Frankfurt or Amsterdam, 2–4 GB, paid by Student Pack
      credits), SSH keys, cloud firewall, Docker.
- [ ] Domain + Caddy HTTPS; images built by GitHub Actions to GHCR; deploy and rollback by tag.
- [ ] Nightly `pg_dump` off-server, restore tested; uptime monitor on `/health.json`.
- [ ] Reachability test of every source from the server; set `dz_proxy` where needed.

**Done when** production runs all verified sources for 48 h with healthy status and a restored
backup has been tested.

## Decisions needed (and when)
| Decision | Needed before |
|---|---|
| Bot contact URL filled in (`SABQBOT_CONTACT_URL`) | M9 |
| ~~Wilaya dataset~~ → 69 + `00` National (2026-10-19) | M2 |
| ~~Organisation access~~ → web app with login only, no organisation RSS feeds (2026-10-19) | M6 |
| ~~Login~~ → email + password, accounts by invitation (2026-10-19) | M6 |
| ~~Email provider~~ → MailerSend over SMTP (2026-10-19) | M6 |
| Sender domain verified in MailerSend (needs the domain) | M9 |
| ~~Breakage alerts~~ → `/health` page only, no push (2026-10-19) | M7 |
| ~~Labelling~~ → none for now; thresholds by judgement + score calibration (2026-10-19) | M8 |
| ~~Server~~ → DigitalOcean first, Hetzner when credits end (2026-10-19) | M9 |
| Domain name | M9 |
| Algerian proxy hosting, if any source needs it | M9 |

## Status
| Track / milestone | Status | Updated |
|---|---|---|
| Step 0 · Repository | done | 2026-10-19 |
| Track A · Investigation | in progress (2 / 17) | 2026-10-19 |
| M1 · Foundation | done, CI green (branch `m1-foundation`) | 2026-10-19 |
| M2 · Data model | done locally (branch `m2-data-model`) | 2026-10-21 |
| M3 · Fetching | todo | |
| M4 · Extraction | todo | |
| M5 · Ingestion | todo | |
| M6 · Login + web app API | todo | |
| M7 · Health | todo | |
| M8 · Story matching | todo | |
| M9 · Deployment | todo | |
