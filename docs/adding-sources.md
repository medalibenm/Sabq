# Adding a source

How we add a source to the catalog **today**: a person investigates with Claude Code, step by step. Typical time: a few minutes per site. (The automated version is in [ai-investigation.md](ai-investigation.md).)

## Flow
1. **Request:** an organisation clicks "Request a source" (stored in `source_requests`), or we decide to add one.
2. **Catalog check:** already in the catalog (same site and language)? → assign the source and requested wilayas to the organisation, done.
3. **Robots and terms:** see step 1 below. Disallowed → refuse, record why, tell the client (e.g. "Reuters doesn't allow automated access; it needs a licence").
4. **Investigate:** steps 2–9 below.
5. **Implement:** write the config (or a small extractor if config can't express it), save fixtures, add a test.
6. **Validate:** all checks in [architecture.md § Validating a config](architecture.md#validating-a-config):
   `python -m sabq.cli catalog validate <slug>` (fixtures) and `--live` (the site), both must pass.
7. **Publish:** add to the catalog, assign its wilaya(s) (or `00` National if it has none), update [sources.md](sources.md), notify the organisation.

## Investigation steps
Stop as soon as a step gives a source that validates.

| # | Step | How | PoC example |
|---|---|---|---|
| 1 | **Robots and terms** | Fetch `robots.txt`; evaluate it for our User-Agent; read any notice. Record the result and date. | Reuters: `Disallow: /` for all + notice → refused. El Mouradia: allowed (a prior assumption said otherwise). |
| 2 | **Reachability** | GET the page with our User-Agent; record status and size. If blocked, try once with a browser UA (only if robots allows us). Note geo-blocking → `egress: dz_proxy`. | Reuters: 401 to both. Others: 200 with ours. |
| 3 | **Known feeds and APIs** | `<link rel="alternate">`, body links with rss/feed/atom, `/feed/`, `/rss`, platform APIs (`/wp-json/`), sitemaps from robots.txt. | AA: feed in `<head>`. AFP: feed link in the body. El Hayat: `/feed/` timeout, WP API works. |
| 4 | **Identify the platform** | Markers in HTML: `wp-content`, `_next`, `__next_f`, `__NUXT__`, Angular bundle names, Drupal paths. | APS: Next.js. El Mouradia: Angular. |
| 5 | **Embedded data** | Search the HTML for ISO dates / IDs inside scripts; decode framework data (JSON-LD, `__NEXT_DATA__`, `self.__next_f.push`). | APS: article objects with `publish_date` in UTC. |
| 6 | **The site's own API** | Record network requests in a browser, or download the JS bundle and search for the backend URL and query patterns. Check robots.txt for the API host too. | El Mouradia: `backend.el-mouradia.dz/article-{lang}s/published`. |
| 7 | **Test the source** | Call it; check fields, item count, languages, categories. | El Mouradia: categories 1 and 2 have items; French collection empty. |
| 8 | **Map fields and URLs** | ID, title, date (+timezone), lead, image, section and wilaya signal; link and image templates (from the site's own routing code if needed). | El Mouradia link `/{lang}/{section}/{_id}`; APS images under `/api/image/`. |
| 9 | **CSS selectors (last resort)** | Only if 3–8 found nothing: listing URLs, link selector, URL/ID pattern, title/date/image selectors; parse visible dates in `Africa/Algiers`. | Not needed in the PoC. |

## Tools to use in Claude Code
- **Bash with `curl` / Python scripts:** raw HTML/JSON, status codes, our User-Agent, saved files to search. Preferred for investigation.
- **Claude in Chrome:** for step 6 on hard sites: load the page and read its network requests directly.
- Not WebFetch: it returns summaries, which hide status codes and raw data.

## What to record in sources.md
Slug, name, URL, language, kind, tier, access method, poll interval, robots status and date,
egress, coverage wilayas and assignment method, notes (quirks, timezones, missing images, empty
sections). Also retain fixtures that exercise repeated listing entries and a cross-source duplicate
so the deduplication rules are tested when the source is added or its config changes.
