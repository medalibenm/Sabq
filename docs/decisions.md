# Decisions and open questions

## Decision log
Newest first. Each entry: date, decision, why.

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
migration later. Names in Arabic and French are taken from the Journal officiel (codes published
2026-06-17) when the seed is written in M2.

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
- **Article body fetching:** for which sources do we fetch full article pages (internal AI use), and how often?
- **Alerts:** channels (email, Telegram, in-app, Slack) and rules, for the next phase.
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
