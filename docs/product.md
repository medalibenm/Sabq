# Product

## What Sabq is
A news radar for journalists. It watches a catalog of sources (news agencies, official institutions, national press), detects new articles quickly, and delivers them as:
- a **web app** where journalists log in and read the news of their organisation's sources and
  wilayas (Sabq is their reader; the frontend is built later);
- **alerts** to journalists (later: AI classification and advanced clustering);
- an **internal JSON API** with full text, for the radar's AI steps.

Organisations get no RSS feeds: the web app, behind login, is the only way to read (2026-10-19).

Many important sources (APS, the Presidency, ministries) publish no RSS. Sabq turns them into a news stream anyway, in our own code, without third-party feed or scraping services.

## Who it's for
Newsrooms and media teams covering Algeria. Sabq is a product for multiple organisations from the
start, not a bespoke product for one named client. The shared catalog avoids fetching the same source
separately for every organisation, while each organisation sees only its enabled wilayas and sources.

## Goals
- **Fast:** median detection delay under 2 minutes on priority sources (60 s polling).
- **Complete:** at least 95% of articles on a source's listing pages are caught.
- **Reliable:** broken sources are detected automatically (silence and quality checks) and fixed quickly.
- **Cheap to run:** polling is plain HTTP; AI is used rarely (adding and repairing sources).
- **Polite and lawful:** robots.txt respected, low request rates, lead-only outputs.
- **Operationally clear:** administrators can see source health, ingestion failures, duplicate groups
  and access assignments without querying the database directly.

## Product decisions (see docs/decisions.md for the log)
- **Curated catalog.** We configure every source ourselves. Clients subscribe to sources; they don't add websites themselves.
- **"Request a source" button.** A client sends a URL; we are notified, investigate, add it to the catalog; every client can then subscribe.
- **Wilaya separation.** Wilayas are first-class product dimensions. A source and an article can be
  associated with one or more wilayas; an organisation is granted explicit wilaya access, and all
  web app reads, alerts and article queries enforce that boundary.
- **Admin UI later.** The first release keeps administration operational and limited; a protected
  admin area for managing organisations, users/roles, wilayas, source assignments, source requests,
  health, and duplicate decisions comes after the ingestion and data model foundations.
- **Deduplication is part of ingestion.** The system keeps each source article, but can group
  articles from multiple sources into one story/event cluster. A cluster may contain any number of
  articles. The representative article is only a display choice, never a replacement for the
  original source articles. Cross-source grouping means **same event**, not same topic, including
  Arabic ↔ French. Automatic matches must be explainable and uncertain matches must remain
  reviewable. How clusters are displayed is decided later with the UI. See
  [story-matching.md](story-matching.md).
- **Manual investigation for now.** We investigate new sites with Claude Code (a few minutes per site). The automated AI investigation is designed ([ai-investigation.md](ai-investigation.md)) but deferred.
- **Build order:** tenancy and access boundaries, extractors and configs, polling, storage,
  deduplication (same-source, then cross-source story matching in the backend), login and the web app API, health
  checks and breakage detection on the health page, and the request button. Then the admin UI (including duplicate
  review), story display and automated AI repair.

## Scope

### In scope now
- Source catalog (multi-language: one source per site per language, e.g. `aps-ar`; a French edition would be a separate `aps-fr`).
- Ingestion: discovery, polling, new/updated article detection, article extraction.
- Storage with versioning of headline/body changes and source observations.
- Multi-organisation accounts with users, roles and explicit wilaya access.
- Wilaya-aware source subscriptions, article filtering, the web app API (behind login), internal API queries and alerts.
- Deduplication within a source and across sources: exact matching first, then semantic story
  matching (automatic at high confidence with no conflicting facts, reviewable candidates below).
  Backend only; display comes later.
- Authenticated API for the web app, internal JSON API, health page. (Frontend later.)
- Per-source egress setting for an Algerian proxy (the proxy itself is separate).

### Later
- Protected admin UI for organisation/user access, wilayas, sources, requests, ingestion health and
  duplicate review/merge/split decisions.
- The web app frontend; displaying story clusters in it and in alerts.
- AI classification, topic clustering and `related` (follow-up) stories, LLM review of uncertain
  pairs, and advanced alert rules.
- Automated AI investigation and repair.
- Social media sources (see open questions in [decisions.md](decisions.md)).

### Out of scope
- Paid wires without a licence (Reuters, AFP wire).
- Anything that requires bypassing robots.txt, bot protection, logins or paywalls.

## Content rules
- The web app and any output shown to organisations show **title, lead, image link and the link to the original** only. Full body text is stored for internal AI processing and never served publicly.
- Respect `robots.txt`, checked live; a disallowed source is marked `blocked_by_robots` and skipped, never worked around.
- Keep request rates low (see [architecture.md](architecture.md)).
