# Architecture

## Core idea
- **Structured data first.** Most sites already expose their articles somewhere: RSS, a platform API, embedded page data, or the site's own internal API. In the PoC, every allowed site had one; no CSS scraping was needed.
- **One generic extractor driven by per-source config.** Site-specific code only when config can't express it.
- **Polling is plain HTTP** (no browser, no AI) using the saved config.
- **AI is used rarely:** to investigate new sites and repair broken configs (manual with Claude Code for now; automated later, see [ai-investigation.md](ai-investigation.md)).

## Ingestion layers

### Layer 1: Structured sources (preferred)
Discovery tries all of these and keeps the best that works:
1. **RSS/Atom anywhere on the page:** `<link rel="alternate">` in `<head>`, **and** body links whose URL or text contains `feed`, `rss` or `atom` (AFP's feed was only linked in the body).
2. **Common feed paths:** `/feed/`, `/rss`, `/rss.xml`, `/atom.xml`, `/index.xml`.
3. **Platform APIs:** e.g. WordPress `/wp-json/wp/v2/posts`. Try several entry points per platform (El Hayat's `/feed/` timed out; its API worked).
4. **Sitemaps:** news or post sitemaps with `lastmod`.
5. **Embedded page data:** JSON-LD, `__NEXT_DATA__` (Next.js pages router), `self.__next_f.push` (Next.js app router, as on APS), Nuxt `__NUXT__`, etc.
6. **The site's own internal API:** JSON endpoints the page calls (as on El Mouradia, a Strapi backend), found via network capture or the JS bundle.

Preference: official feeds/APIs → embedded data → internal APIs. Record which one is used (`access_method`).

### Layer 2: Config-driven extraction
One generic extractor, driven by a per-source config, supporting three kinds of source:
- **Feed:** RSS/Atom URL, plus fixes if needed (AFP sends ISO dates and `http` links).
- **JSON** (API or embedded data): URL, where the item list is, and a **field mapping** (e.g. `id → $._id`, `title → $.title`, `date → $.publish_date`, `lead → $.introtext`, `image → $.cover.url`).
- **HTML** (CSS selectors, last resort): listing URLs, link selector, title/date/image selectors.

Shared by all three:
- **URL templates** for links and images, with value maps (e.g. `https://www.el-mouradia.dz/ar/{section}/{_id}` with category `1 → president`, `2 → presidency`; `https://www.aps.dz/fr/api/image/{url}`).
- **ID rule:** the site's own ID (field, or regex on the URL, e.g. APS's 8-char code), else the normalised URL.
- **Date rule:** which field or text, its format, its timezone (e.g. `Africa/Algiers`).
- **Multiple listings per source** (homepage + sections), merged and de-duplicated by ID.

Built in `sabq.extract` (M4). Each source is one YAML file in `catalog/`, validated in full when
the catalog is read (unknown keys are errors). The format is documented at the top of
`backend/src/sabq/extract/config.py`; example (`catalog/mouradia-ar.yaml`, shortened):

```yaml
slug: mouradia-ar
name: رئاسة الجمهورية
home_url: https://www.el-mouradia.dz/ar/presidency
language: ar
kind: official
tier: priority
poll_interval_s: 300
access_method: json_api           # rss | wp_json | json_api | embedded (html: later)
robots: {checked_at: 2026-10-21, result: allowed}
listings:
  - https://backend.el-mouradia.dz/article-ars/published?_start=0&_limit=30&_sort=date:DESC,createdAt:DESC
items: $[*]
fields:                           # small JSONPath subset: $.a.b, $['wp:x'][0], $[*]
  id: $._id                       # or {path: $.alias, regex: '([a-z0-9]{8})-'} (first group)
  title: $.title
  published: $.date
  lead: [$.subTitle, $.content]   # first non-empty; cleaned, shortened to lead_max_chars
  image: $.cover.url
  section: $.category
value_maps:
  section: {"1": president, "2": presidency, _default: presidency}
templates:                        # {name:path} percent-encodes the value (APS links)
  link: https://www.el-mouradia.dz/ar/{section}/{id}
  image: https://backend.el-mouradia.dz{image}
exclude: {}                       # e.g. APS: {alias: '^(dossier|infographie|video)/'}
dates: {published_tz: UTC, confidence: source_meta}   # zone for naive dates
link_check: skip                  # same page for every URL; validation can't check titles
```

Feeds are read with `feedparser`, so feed fields are paths into its entries (`$.title`, `$.link`,
`$.id`, `$.published`, `$.summary`, `$.enclosures[0].href`). Embedded data: `embedded: {kind:
next_f, object_start: '{"id_article":'}` (APS). Items without ID, title or link are rejected and
counted, never guessed; an unreadable date leaves the article at `first_seen` confidence and is
reported. Validation: `python -m sabq.cli catalog validate [SLUG] [--live]` (see
[Validating a config](#validating-a-config)).

### Layer 3: AI investigation and repair (rare)
Find the data source for a new site, or repair a broken config. Done **manually with Claude Code** today ([adding-sources.md](adding-sources.md)); automated design in [ai-investigation.md](ai-investigation.md).

### Layer 4: Shared foundations
- **Polite fetching:** our User-Agent (`SabqBot/<version> (+contact URL)`; a browser UA only if a site rejects ours and robots.txt doesn't forbid us), robots.txt checked live and cached 24 h, one request at a time per host, ±20% jitter on intervals, `ETag`/`If-Modified-Since`, exponential backoff on 429/5xx, 15 s timeouts.
  Built in `sabq.fetch` (M3): every request goes through `Fetcher.get`, which checks robots.txt for
  each origin it touches (redirects are followed hop by hop, so a redirect to another host checks
  that host's robots.txt too), keeps requests to one host at least 5 s apart or the site's
  `Crawl-delay` if longer (each gap 0–20 % longer), backs off 60 s → 120 s → … → 1 h after 429,
  5xx or network errors (or the site's `Retry-After`, honoured up to a day) without sending
  anything meanwhile, and refuses responses over 20 MB. robots.txt answers: 2xx = rules; 401/403 =
  everything disallowed; other 4xx = no robots.txt, allowed; 429/5xx/unreachable = nothing fetched,
  retried after 15 min. All values are settings (`FETCH_*`, `ROBOTS_*`).
- **Egress:** per-source `egress: default | dz_proxy`; sources marked `dz_proxy` go through `DZ_PROXY_URL` (for geo-blocked `.dz` sites; the server will be in the EU).
- **Article pages:** `og:` tags and JSON-LD first, then body extraction with trafilatura.
- **New vs known:** new `external_id` → fetch the article once. Known → re-fetch only if the listing shows a changed title/date, or every N hours during the first 24 h; bump `version` when `content_hash` changes.
- **Dates:** machine-readable metadata first, then visible text parsed with `dateparser` (`fr`, `ar`) in `Africa/Algiers`, then first-seen time. Always store UTC plus a confidence field.
- **Text:** Arabic stored as-is (NFC normalised), never transliterated; percent-encoded URLs decoded for display, kept encoded for fetching.
- **Headless browser** only for investigation, or as a last-resort fetcher for a site that renders
  only client-side and exposes no usable feed, API, sitemap or embedded data. A JavaScript-rendered
  page is not automatically a browser job: first inspect its network/API responses and embedded
  state. If a browser is required, keep it isolated, rate-limited and covered by saved fixtures;
  do not use it to bypass robots.txt, bot protection, logins or paywalls.

## Data model (multi-tenant and wilaya-aware)
Sources are a **shared catalog** fetched once. Organisations subscribe to sources and are granted
access to wilayas; ingestion is shared, while every organisation-facing read is filtered by that
access. No organisation can infer the existence of another organisation's users, notes or access
assignments.

- `organisations(id, slug, name, status[active|suspended], created_at)`
- `users(id, organisation_id, email, display_name, password_hash, role[owner|admin|editor|viewer], status[invited|active|disabled], created_at, last_login_at)`
- `user_sessions(id, user_id, created_at, expires_at, last_seen_at)`; `auth_tokens(id, user_id, kind[invite|reset], token_hash, expires_at, used_at)`.
- `wilayas(id, code, name_ar, name_fr, enabled, active_from, created_at)`: the 69 official wilayas
  (59–69 active from 2027-01-01), plus one special row **`00` National** (`وطني` / `National`) for sources without a local wilaya.
- `organisation_wilayas(organisation_id, wilaya_id, enabled)`; an organisation must have at least
  one enabled wilaya before it can receive articles.
- `sources(id, slug, name, home_url, language, kind[official|agency|national|local|international], tier[priority|normal|secondary], poll_interval_s, access_method[rss|wp_json|sitemap|embedded|json_api|html|headless], config jsonb, config_version, egress[default|dz_proxy], enabled, status, robots_checked_at, created_at)`. One row per source per language.
- `source_config_versions(source_id, version, config, changed_by, reason, created_at)`
- `source_wilayas(source_id, wilaya_id, assignment_method[manual|source_section|article_rule], enabled)`.
  Every source has at least one row: a local source gets its wilaya(s), any other source gets
  `00` National. See [Wilaya assignment](#wilaya-assignment).
- `organisation_sources(organisation_id, source_id, enabled)`; effective visibility is the
  intersection of organisation sources and organisation wilayas.
- `source_requests(id, organisation_id, requested_by, url, note, status[new|investigating|added|refused], reason, created_at)`.
- `fetch_runs(id, source_id, started_at, finished_at, http_status, items_seen, items_new, items_updated, error, duration_ms)`
- `articles(id, source_id, external_id, url, canonical_url, canonical_url_key, title, lead, body_text, image_url, author, section, language, published_at, published_at_confidence[source_meta|page_text|first_seen], modified_at, first_seen_at, last_seen_at, content_hash, version)`, unique on `(source_id, external_id)` and on `(source_id, canonical_url_key)`.
  Plus `match_text` and `match_signals jsonb` for story matching.
- `article_wilayas(article_id, wilaya_id, assignment_method[source|section|entity|manual], confidence)`.
- `article_embeddings(article_id, model, embedding vector(1024), created_at)`, primary key `(article_id, model)`, HNSW index (pgvector). `articles.embedding_status[pending|done|failed]`.
- `story_clusters(id, representative_article_id, status[candidate|automatic|confirmed|split|rejected], first_published_at, last_member_at, closed_at, created_at, updated_at)`
- `story_cluster_members(cluster_id, article_id, membership[duplicate|related], confidence, evidence jsonb)`, unique on `(cluster_id, article_id)`.
- `story_matching_config(version, thresholds, windows, weights, created_by, created_at)`.
- `article_versions(article_id, version, title, lead, content_hash, seen_at)`
- `dedup_candidates(id, kind[article|cluster_merge], article_id, candidate_article_id, score, signals jsonb, scorer_version, status[pending|confirmed|rejected], reviewed_by, reviewed_at)`.
- `audit_events(id, organisation_id, user_id, actor, action, entity_type, entity_id, details, created_at)` for
  admin mutations, especially access changes and cluster merge/split decisions.

`canonical_url_key` is generated by a shared normalizer: resolve relative URLs, lowercase the
host, remove fragments, remove known tracking parameters, normalize default ports and trailing
slashes, and preserve meaningful query parameters. It is not a substitute for source identity:
the `(source_id, external_id)` key remains authoritative when the source supplies a stable ID.

Deduplication runs in this order:
1. Merge repeated listing/API observations by `(source_id, external_id)`, then by
   `(source_id, canonical_url_key)`.
2. Find cross-source candidates (other sources, ±36 h) by semantic similarity of title + lead
   (Voyage AI `voyage-4` embeddings, pgvector) plus same-language lexical overlap.
3. Group automatically when cosine similarity ≥ 0.90 and no hard conflict (numbers, wilaya, event
   date, counterpart); 0.85–0.90 or a conflict becomes a `pending` candidate for review. Numbers,
   places, entities and time are stored as explainable signals. Thresholds are initial values,
   confirmed by evaluation.
4. A cluster may contain any number of articles. New articles are compared with existing cluster
   members and can join when they match the same event, not only one particular article.

Normalization, signals, candidate search, scoring, thresholds, cluster assignment and evaluation
are specified in [story-matching.md](story-matching.md).

A story cluster represents the subject/event, not a replacement article. Every source article and
its source URL remain stored. `representative_article_id` is only a display choice (earliest
reliable publication time, then source tier, then earliest observation), and can change when a
better member arrives. The future UI may hide cluster members in the main feed and show them on a
dedicated story/duplicates page. That presentation decision does not change ingestion, storage or
cluster membership.

The web app can later offer two modes: all source articles, or one representative article per cluster
with a count/link to the remaining members. A split removes membership without deleting source
observations or article versions; a merge is reversible.

### Wilaya assignment
v1 (2026-10-19): **by source only.**
- Each source is linked to its wilaya(s) in `source_wilayas` when it is added (wilaya listed in
  [sources.md](sources.md)). A source with no wilaya is linked to `00` National.
- Every article inherits its source's wilayas in `article_wilayas`
  (`assignment_method = source`, `confidence = 1.0`). No text analysis in v1.
- `00` National is granted like any other wilaya; it is granted to every new organisation by
  default and can be removed.
- Later, in this order of strength: regional **sections** (`section`), place names and datelines
  in the title/lead (`entity`, reusing the story-matching place list, with care for ambiguous
  Arabic names such as الجزائر, معسكر, البيض, الوادي), and admin corrections (`manual`). These
  can add wilayas to an article from a national or local source.

**Detection delay** = `first_seen_at - published_at`, stored per article and shown on the health page.

## Outputs
Organisations read through the **web app behind login**; there are no organisation RSS feeds
(decision 2026-10-19).
- **Auth:** email + password. Accounts are created by invitation only: a Sabq admin, or an
  organisation `owner`/`admin` for their own organisation, invites an email; the user sets a
  password through a single-use invite link (valid 72 h). Password reset by email link (valid
  1 h, single use). Passwords hashed with Argon2id; server-side sessions in an `HttpOnly`,
  `Secure`, `SameSite=Lax` cookie; login attempts rate-limited; invites, resets and role changes
  written to `audit_events`. Endpoints: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`,
  `POST /auth/invite`, `POST /auth/accept-invite`, `POST /auth/forgot`, `POST /auth/reset`.
  Users belong to one organisation and have a role. Every web app request is authenticated.
  Emails go through **MailerSend** over standard SMTP (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASSWORD`, `EMAIL_FROM`), so the provider can change by settings only. In development,
  a local Mailpit container catches all emails (`compose.override.yaml`).
- **Web app API** (`/app/...`): article stream with filters (wilaya, source, language, since,
  search), article detail, the user's sources and wilayas, source requests. Returns title, lead,
  image, original link, source, wilayas, dates, and story-cluster info; **never** `body_text`.
  Organisation and wilaya filtering is enforced on the server for every query.
- `GET /admin/feeds/{source_slug}.xml`: RSS 2.0 per source, **admin only**, for checking a source
  (lead only, valid RSS, `feedparser` bozo check in tests).
- `GET /api/articles?organisation=&wilaya=&source=&since=&lang=`: internal JSON, may include
  `body_text`; organisation and wilaya authorization is mandatory.
- `GET /health` (HTML) and `GET /health.json`: per source: last successful fetch, last error, items in last 24 h, median detection delay, `access_method`, status, and a **silence warning** when a source returns zero links or no new item for longer than 3× its usual gap.
- Planned admin UI: organisation and user/role management; wilaya and source assignments;
  source-request workflow; source health and fetch runs; article/story-cluster inspection; and
  deduplication review with confirm, reject, merge and split actions. All mutations are audited.

## Validating a config
A config (new or repaired) goes live only if all pass. `python -m sabq.cli catalog validate`
runs the automatic ones against the saved fixtures (two listing snapshots, article pages) and,
with `--live`, against the site through the polite fetcher (each listing, the first again, three
article links, two images); the test suite runs it for every catalog source:
- **Item count** is sensible (similar to the page, or to before for a repair).
- **Known items** are included (for a repair).
- **Links open the article:** fetch a few; the **article title appears on the page** (compare after HTML-unescaping, against `og:title` or `<h1>`). A 200 alone is not enough: JavaScript-built sites return the same page for every URL (El Mouradia). For such sites, render one link in a headless browser.
- **Images load:** 200 and an image content type (APS's own `og:image` URL is 404; real images are under `/api/image/`).
- **Dates are right:** parse, recent, not in the future, and match the date shown on the page (APS: 11:46 UTC = 12:46 Algiers).
- **No noise:** no sidebars ("most read", "related") or non-articles (APS dossiers, infographics, videos).
- **IDs unique and stable** across two fetches.
- **Deduplication is stable:** repeated entries from multiple listings create one source article;
  URL tracking parameters do not create a second article; exact cross-source matches create one
  story cluster; the story-matching fixtures (same-event, lookalike and ar ↔ fr pairs) pass; and
  pairs below the automatic threshold or with a conflict remain reviewable, not merged.
- **Wilaya boundaries hold:** a source and article assigned to one wilaya do not appear in another
  organisation's or wilaya's web app/API response without an explicit assignment.

## Source statuses
`ok` · `degraded` (some fields missing) · `broken` (extraction failing; repair needed) · `empty` (valid, no content, e.g. El Mouradia French) · `blocked_by_robots` · `unreachable` (e.g. geo-blocked, outage).

## Breakage detection
Flag a source as broken when:
- zero links, or far fewer than usual;
- title/date/image empty on most items;
- dates fail to parse or look wrong;
- the ID or URL pattern stops matching;
- no new items for more than 3× the usual gap;
- an error status or changed format (an internal API changed its fields).

Before treating it as broken: rule out outages (status, response size, blocking pages), and tell **empty** apart from **broken** (empty → no repair, recheck occasionally).

Repair today: the source shows as broken on `/health` (no push alerts, decision 2026-10-19); we check it, fix the config with Claude Code and save a new config version. Later: automated repair ([ai-investigation.md](ai-investigation.md)).

## Planned stack
- Python 3.12, FastAPI, `httpx2` (async, HTTP/2), `protego` (robots.txt, RFC 9309), `feedparser` (reading feeds), `selectolax` or `lxml`, `trafilatura`, `feedgen`, `dateparser`, `pydantic`.
- PostgreSQL 16 via Docker Compose; SQLAlchemy 2 + Alembic; `pgvector` for story-matching embeddings.
- Embedding API for story matching: Voyage AI `voyage-4` via OpenRouter (~$0.30/month at the
  expected volume), behind a provider-neutral, OpenAI-compatible interface.
- Scheduler: in-process `asyncio` loop or APScheduler (no Redis at first).
- Playwright (Chromium) only for investigation and as a last-resort fetcher.
- `uv`, `ruff`, `pytest` (offline tests on saved fixtures); Docker Compose (services below).

## Deployment
Sabq is built to run on **one small EU server with Docker Compose** from the start. Requirements:
2 vCPU, 4 GB RAM, ≥ 40 GB disk, Ubuntu LTS, Docker Engine + Compose v2, EU region. Two
interchangeable providers; the code must not depend on either:
- **DigitalOcean** Droplet (Frankfurt or Amsterdam), basic 2 vCPU / 4 GB, ~$24/month, covered at
  first by the GitHub Student Pack credits.
- **Hetzner** CX22 (Germany/Finland), ~€6–8/month with backups and domain; the cheaper option once
  credits run out. Every component must run with `docker compose up` on a fresh
machine; nothing is installed on the host except Docker. The same files run locally and in
production.

### Services
| Service | Image | Role | Memory budget |
|---|---|---|---|
| `db` | `pgvector/pgvector:pg16` | PostgreSQL 16 + pgvector; volume `pgdata`; port never published | ~1 GB (`shared_buffers` 512 MB) |
| `app` | Sabq image, `uvicorn` | FastAPI: auth, web app API, internal API, health pages | ~300 MB |
| `worker` | same Sabq image, worker command | scheduler, polling, article fetching, story matching (calls the embedding API) | ~300–500 MB |
| `proxy` | `caddy:2` | reverse proxy, automatic HTTPS; only service exposing ports 80/443 | ~50 MB |

- **One image, two commands** (`app`, `worker`). Polling runs only in `worker`, so restarting the
  API never stops polling, and exactly **one** `worker` runs (no duplicate schedulers).
- The total is ~2 GB, so a 2 GB server (DigitalOcean ~$12/month) can work with 2 GB of swap;
  4 GB is the comfortable size. Scale up by resizing the server; move
  `db` to its own server only when needed.

### Build rules
- **Configuration from environment variables**, read with pydantic settings: `DATABASE_URL`,
  `DZ_PROXY_URL`, `SABQBOT_CONTACT_URL`, `PUBLIC_BASE_URL`, `LOG_LEVEL`, etc. A committed
  `.env.example` lists them; the real `.env` is never committed. No secrets in code or images.
- **Embeddings via API** (OpenRouter: `OPENROUTER_API_KEY`, `EMBEDDING_MODEL=voyageai/voyage-4`,
  `EMBEDDING_BASE_URL`): no model in the image. Calls are batched, have a
  timeout and retries, and an outage only delays matching (`embedding_status = pending`).
- **Migrations** with Alembic, run by the one-off `migrate` service before `app` and `worker`
  start (`docker compose up` waits for it to finish successfully). Migrations stay backward compatible for one
  release so a rollback does not break the database.
- **Health checks** on every service in `compose.yaml`; `restart: unless-stopped`.
- **Logs** as JSON to stdout, Docker log rotation (`max-size`, `max-file`).
- **Containers run in UTC**; local time only through `Africa/Algiers` conversion in code.
- **Graceful shutdown:** the worker finishes or abandons in-flight fetches cleanly on `SIGTERM`.
- Local development uses `compose.override.yaml` (code reload, Mailpit, `db` on host port 5440 and
  `app` on 8010, both configurable to avoid clashes with other local projects); production uses
  `compose.yaml` only (`docker compose -f compose.yaml ...`).

### Release and operations
- Images built by GitHub Actions, tagged with the git commit SHA, pushed to GitHub Container
  Registry. Deploy = on the server, set the tag, `docker compose pull`, migrate,
  `docker compose up -d`. Rollback = previous tag.
- **Backups:** nightly `pg_dump` to off-server, S3-compatible storage (DigitalOcean Spaces or
  Hetzner Object Storage / Storage Box), kept 14 days, restore tested; plus the provider's server
  backups.
- **Portability:** moving provider = new server, restore the latest dump, copy `.env`, point DNS.
  Test this once before the first client.
- **Security:** SSH keys only, provider cloud firewall + `ufw` allowing 22/80/443, `db` reachable only on
  the internal Compose network, automatic security updates.
- **Monitoring:** `/health.json` checked by an external uptime monitor; source health as in
  [Outputs](#outputs).
