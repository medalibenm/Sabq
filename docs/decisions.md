# Decisions and open questions

## Decision log
Newest first. Each entry: date, decision, why.

### 2026-10-21 · No journalist alerts in the first release
The live web app (with server push) is the alert for now. Alert channels (browser notifications,
email, Telegram) and rules (keywords, wilayas) are designed after the first organisations use
Sabq. Nothing in ingestion depends on this.

### 2026-10-21 · Live updates by server push (SSE)
The web app receives new articles by Server-Sent Events, not by polling. The worker announces
each new (non-baseline) article with PostgreSQL `NOTIFY` in the same transaction that stores it,
so there is no extra service (no Redis); the app `LISTEN`s and pushes to each connected user only
the articles that user may see (the same access filter as every other read). The proxy must not
buffer the stream (Caddy `flush_interval -1`), and clients reconnect with `Last-Event-ID`.

### 2026-10-21 · First poll is a baseline
When a source is polled for the first time, or after more than 24 h without a successful poll,
the articles already in its listings are stored as **baseline**: visible in the web app by their
publication date, but never counted as new, never pushed or alerted, and without a detection
delay. Only articles that appear after that are new. Adding a source never causes a burst of
old "news".

### 2026-10-21 · Article pages fetched only when the config asks
The worker fetches a new article's own page only for sources whose config has an
`article_page` section (today: Djelfa Info, whose feed has no lead), and only to fill what the
listing lacks (lead, image, date, author). Listing data always wins. At most 20 pages per poll,
never for baseline articles. Full text for internal use is not fetched in v1.

### 2026-10-21 · Extraction: one strict config format, no per-site code
All seven catalog sources (the four from the PoC and the three from Track A) are YAML configs read
by one extractor (`sabq.extract`); the PoC's per-site Python is gone. Field paths use a small
JSONPath subset written for us (`$.a.b`, `$['k'][0]`, `$[*]`) rather than a library: it covers
every source and fails on anything else. Feeds are read with `feedparser` (tolerant of broken
feeds). The catalog schema is strict: an unknown key is an error at load, so a typo can't
silently disable a field. Items missing ID, title or link are rejected, never guessed (precision);
an unreadable date keeps the article with `first_seen` confidence. `canonical_url_key` treats
http/https and a leading `www.` as the same (it is per source, so this is safe). A config goes
live only after `catalog validate` passes on fixtures and `--live`.

### 2026-10-21 · Fetching: httpx2 + protego; how robots.txt answers are read
The fetch client is `httpx2` (the maintained successor of `httpx`; Starlette 1.9 already prefers
it): async, HTTP/2 via its `http2` extra, proxies for `dz_proxy`, and a mock transport for tests.
robots.txt is parsed with `protego` (Scrapy's RFC 9309 parser) instead of Python's
`urllib.robotparser`, which applies the first matching rule instead of the most specific one and
ignores `*` / `$` wildcards, so it can allow a path a site disallows. Reading the answer to
`/robots.txt`: 2xx = its rules; **401/403 = everything disallowed** (RFC 9309 would allow, but a
site refusing us its robots.txt is refusing us; we never work around it); other 4xx = no
robots.txt, allowed; 429/5xx/network error = unreachable, nothing is fetched and it is retried
after 15 minutes. Requests to one host are at least 5 s apart (or the site's `Crawl-delay`).

### 2026-10-21 · Track A status `inactive` for sites that stopped publishing
La Dépêche de Kabylie (15 Tizi Ouzou) is reachable and allowed, but its newest article is from
2021-06-28. Such sources get the status `inactive`: recorded in [sources.md](sources.md), not
added to the catalog, rechecked now and then.

### 2026-10-19 · Repository layout: one backend package, split by domain
The repository is split at the top (`backend/`, later `frontend/`, `catalog/`, `deploy/`,
`docs/`), but the backend is **one** Python package with two entry points (`app`, `worker`) in one
Docker image, organised by domain (`fetch`, `extract`, `ingest`, `matching`, `auth`, `api`), not
`/services/api` + `/services/worker`. The two services share models, settings, extraction and
matching, so separate packages would mean duplicated or extra shared code for no benefit at this
size. A domain folder can still be moved out into its own service later.

### 2026-10-19 · Production starts on DigitalOcean
The first production server is a DigitalOcean droplet in Frankfurt or Amsterdam (2–4 GB), paid by
the GitHub Student Pack credits. Hetzner stays the planned move when credits run out; the setup is
provider-neutral so the move is a restore and a DNS change.

### 2026-10-19 · Story-matching thresholds by judgement, no labelling for now
No hand-labelled evaluation set for now. Automatic grouping at cosine ≥ 0.90 with no hard
conflict, review at 0.85–0.90. Before switching automatic grouping on, a calibration on real
articles (noise floor, same-topic lookalikes, copied wires) checks that 0.90 sits above the
lookalikes for `voyage-4`; if not, the threshold is raised. A journalist-labelled set comes later.

### 2026-10-19 · Transactional email: MailerSend over SMTP
Invites and password resets are sent with MailerSend. The code uses plain SMTP settings, not a
provider SDK, so switching provider is a settings change. Development uses a local Mailpit
container. The sender domain must be verified in MailerSend before production (needs the domain).

### 2026-10-19 · Source breakages shown on the health page only
No push alerts to the Sabq team for now: broken, silent, blocked and unreachable sources are shown
first on `/health`, with how long they have been in that state, and we check it ourselves.
Revisit (Telegram or email) when the catalog grows and a missed breakage costs clients news.

### 2026-10-19 · Login: email + password, accounts by invitation
Users sign in with email and password. There is no public sign-up: a Sabq admin, or an
organisation owner/admin for their own organisation, invites a user by email, and the user sets a
password from a single-use link. Password reset by email. This needs a transactional email
provider (choice open). Details in [architecture.md](architecture.md#outputs).

### 2026-10-19 · Web app with login is the only organisation output; no organisation RSS feeds
Journalists read Sabq in our own web app (Sabq acts as their reader), behind user login. The
backend exposes an authenticated web app API with organisation and wilaya filtering enforced on
the server. Organisations get no RSS feeds; per-source RSS remains only as an admin tool for
checking sources. Content shown stays title, lead, image and original link. The frontend is built
later.

### 2026-10-19 · 69 wilayas + `00` National
The `wilayas` table holds all **69** official wilayas (codes 01–69; the 11 created by the 2025
amendment of the territorial organisation law, codes 59–69, become operational on 2027-01-01) plus
`00` National. The new ones carry `active_from = 2027-01-01` so they exist from day one without a
migration later. Codes 59–69 and their Arabic/French names come from the arrêté in Journal
officiel n° 50 of 15 July 2026 (59 Aflou, 60 Barika, 61 El Kantara, 62 Bir El Ater, 63 El Aricha,
64 Ksar Chellala, 65 Aïn Ouessara, 66 Messaad, 67 Ksar El Boukhari, 68 Bou Saâda, 69 El Abiodh
Sidi Cheikh). A press list from November 2025 gave different numbers; the JO is authoritative.

### 2026-10-19 · Bot contact URL optional until production
The User-Agent is `SabqBot/<version>` during investigation and development, with
` (+<contact URL>)` appended from `SABQBOT_CONTACT_URL` once it is set. It must be set before
production (plan M9), so site owners can identify and reach us.

### 2026-10-19 · Wilaya assignment by source; `00` National for the rest
For now an article's wilaya is its source's wilaya, set when the source is added (local sources
listed by wilaya in [sources.md](sources.md)). Sources without a wilaya, including all current
verified sources (APS, Presidency, El Hayat, Anadolu) and regional ones such as El Chark El Youm,
belong to a special wilaya `00` National, granted to every new organisation by default. Section-,
place-name- and manual assignment come later. Simple, predictable and good enough while local
coverage comes mostly from local sources.

### 2026-10-19 · Catalog: APS in Arabic only; AFP corporate removed
`aps-fr` and `afp-corporate-fr` are removed from the catalog; APS is followed in Arabic only
(`aps-ar`). The verified catalog is now `aps-ar`, `mouradia-ar`, `elhayat-ar`, `aa-ar`, all Arabic.
AFP's corporate feed was news about AFP itself, not the wire. PoC configs and fixtures stay as
reference. Cross-language story matching stays in the design for French sources added later.

### 2026-10-19 · Story-matching embeddings from the Voyage AI API (`voyage-4`) via OpenRouter
Embeddings come from an API instead of a local model: `voyage-4` (multilingual incl. Arabic and
French, 1024 dimensions, $0.06 per 1M tokens), called through OpenRouter's OpenAI-compatible
embeddings endpoint, about $0.30/month at ~5M tokens/month. An API model is
expected to match Arabic ↔ French more precisely than a small local model, which matters most
because a wrong merge hides news. `voyage-4-lite` and OpenAI `text-embedding-3-small` are cheaper
but weaker for this. Only title and lead (public text) are sent. An API outage delays matching and
never loses an article. The embedder is behind one interface so the provider can change. No model
runs on the server, so it needs less memory. Replaces the local `multilingual-e5-small` proposal.

### 2026-10-18 · Hosting: one EU server with Docker Compose (DigitalOcean or Hetzner)
Sabq runs on one EU server (2 vCPU, 4 GB) using Docker Compose (`db` with pgvector, `app`,
`worker`, `proxy`). Provider: **DigitalOcean** (Frankfurt/Amsterdam, ~$24/month, paid at first by
GitHub Student Pack credits) or **Hetzner** CX22 (~€6–8/month, cheaper once credits end). Nothing
in the code depends on the provider, so moving is a restore + DNS change. The expected load is
tiny (e.g. 18 sources at 5–30 min ≈ 66 requests/hour), so cost is driven by memory for PostgreSQL,
not traffic. Vercel's free plan was ruled out (non-commercial only, no
always-on poller). The code is built for this deployment
from the start; rules in [architecture.md](architecture.md#deployment).

### 2026-10-18 · Story matching: same event, backend first, precision over recall
Cross-source deduplication means detecting articles from different sources that report the
**same event** (not the same topic), including across Arabic and French. It is built in the backend
now; how clusters are displayed waits for the UI design. Matching combines a multilingual
embedding of title + lead (pgvector) with lexical overlap, numbers, places, entities and time, and
assigns articles to open clusters by average-of-best-two scores to avoid chaining. A wrong merge
hides news, so precision is favoured. Initial rule: articles group automatically at embedding
cosine ≥ 0.90 with no hard conflict (numbers, wilaya, date, counterpart); 0.85–0.90 or a conflict
becomes a pending review candidate. These values are a starting point, checked by a
score calibration on real articles (2026-10-19: no hand-labelled set for now). Details: [story-matching.md](story-matching.md).

### 2026-10-18 · Multi-organisation product with wilaya boundaries
Sabq is not scoped to a single first client. Multiple organisations are
supported from the first release. Wilayas are first-class access boundaries: organisations receive
explicit wilaya grants, sources can cover one or more wilayas, and every organisation-facing feed/API
request enforces both organisation and wilaya access. The access model is in scope before the admin
UI; the protected admin UI for managing organisations, users and roles, wilayas, sources, health,
requests and duplicate decisions is later.

This keeps ingestion and the curated source catalog shared while preventing cross-organisation
data leakage and making local coverage separable from national coverage.

### 2026-10-18 · JavaScript-rendered sites use a structured fallback ladder
A JavaScript-rendered page is not automatically fetched with a browser. Sabq first looks for the
site's RSS/Atom feed, platform API, sitemap, embedded framework state or internal JSON API. A
headless browser is the last resort when no usable data source exists, and is isolated, rate-limited,
fixture-tested and never used to bypass robots.txt, bot protection, logins or paywalls.

### 2026-10-18 · Source observations and story clusters for deduplication
An article observed by a source is retained as an immutable source-level record, identified first by
the source's stable external ID and then by a normalized canonical URL. Articles from multiple
sources that report the same subject/event are grouped into a reversible story cluster, which may
contain any number of members. Matching uses title similarity plus time, entities/locations,
wilaya/section overlap and lead similarity; title similarity alone is not sufficient. A
representative article is selected only for display and never replaces the original articles.
Similarity matches retain explainable signals and are not silently merged without a later review
workflow. The future UI may hide cluster members in the main feed and expose them on a dedicated
story/duplicates page; that is a presentation decision, not a storage rule.
*Updated by "Story matching" above: automatic grouping is allowed at cosine ≥ 0.90 with no
conflicting facts; below that, matches remain reviewable.*

### 2026-10-18 · Project name: Sabq (سبق)
"Scoop" / "being first". Note: a Saudi outlet uses "Sabq" (sabq.org); check domain and trademark before public launch.

### 2026-10-18 · Curated catalog, no client self-service (for now)
Clients are similar newsrooms wanting the same sources. We configure sources; clients subscribe and can **request** a source. Self-service adds complexity with no current benefit. Revisit when requests outpace us or niche sources are needed.

### 2026-10-18 · Manual investigation with Claude Code; automated AI deferred
Adding a site takes minutes by hand. Build automated **repair** first when breakages become frequent; automated onboarding only with self-service.

### 2026-10-18 · Own tools feed the LLM; no provider web fetching
When AI investigation is automated, our tools gather and clean evidence; the LLM only judges. Plain functions via API tool use; MCP wrapper only if needed later.

### 2026-10-17 · Structured data first, CSS selectors last
All allowed PoC sites had structured data (RSS, platform API, embedded data, internal API). Selector extraction stays as the fallback.

### 2026-10-17 · Reuters refused
robots.txt disallows all, written notice forbids automated collection, active bot protection. Only route: a licence.

### 2026-10-13 · No third-party feed or scraping services
Everything runs in our own code (from the original brief). Exceptions must be recorded here.

## Open questions
- **Languages:** ar + fr only, or en / Tamazight too?
- **Tiers and intervals** per source (see [sources.md](sources.md)).
- **Social media:** YouTube (public RSS) and Telegram (official API) are easy. X is paid. Facebook Pages need Meta's "Page Public Content Access" approval; third-party scrapers (Apify etc.) break Meta's terms, are fragile and raise personal-data issues (GDPR on an EU server). Decision with legal review.
- **Internal APIs and embedded data** (El Mouradia, APS) are undocumented and can change; acceptable under each site's terms? Legal review.
- **Algerian proxy:** which `.dz` sources need `dz_proxy` from the EU server? Reachability test
  from the EU server; where and at what cost to host the proxy.
- **DigitalOcean credits:** amount and expiry date of the GitHub Student Pack credits; plan the
  move to Hetzner before they run out if cost matters.
- **Article body fetching:** full text for internal use (AI, matching) is not fetched in v1;
  revisit with story matching or AI features.
- **Alerts:** channels (browser, email, Telegram, Slack) and rules, after the first release.
- **Automated AI later:** which model, prompt and config format; human approval rules for repairs.
- **Pricing and organisation limits.**
- **Wilaya taxonomy:** regional sources (e.g. East): keep as National, or link to each wilaya of the region?
- **Similarity thresholds:** confirm the initial 0.90 (automatic) / 0.85 (review) values, and
  whether same-language and ar ↔ fr pairs need different thresholds, by calibration now and a
  journalist-labelled set later ([story-matching.md](story-matching.md#calibration-and-evaluation)).
- **Story matching model:** confirm `voyage-4` during calibration (and ar ↔ fr once French sources exist) (compare with
  `voyage-4-large` if precision is short); check OpenRouter's and Voyage's data-use terms (training opt-out in OpenRouter privacy settings); who
  labels the pairs (a journalist's judgement of "same event" is the reference).
- **Story display:** how clusters appear in the web app and alerts; decided with the UI.
