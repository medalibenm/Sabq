# Proof of concept: lessons

Run 2026-10-17 on 6 sites. One small extractor per site generated valid RSS 2.0 feeds (no `feedparser` errors), with links, images and dates spot-checked against the live sites. Code, fixtures and tests are kept in the separate PoC folder (`Documents/PoC RSS`) as a reference.

## Results

| Site | What worked | Type | Notes |
|---|---|---|---|
| El Hayat | WordPress REST API | Platform API | `/feed/` timed out; the API worked |
| APS (ar, fr) | Article data embedded in the Next.js page | Embedded data | UTC dates in the data; `og:image` URL is 404, real images under `/api/image/`; 3 listings overlap, de-duplicated by ID |
| El Mouradia | The site's own Strapi API | Internal API | Found by reading the JS bundle; links built from ID + category; SPA returns 200 for every URL; French collection empty; robots.txt allows all (the original brief wrongly assumed it was blocked) |
| AFP (corporate) | The site's own RSS feed | Feed | Linked in the body, not `<head>`; ISO dates are invalid RSS, so the feed is re-published |
| Anadolu (ar) | Official RSS, advertised in `<head>` | Feed | Found by discovery alone; dates +03:00 → UTC; no images; items not in date order |
| Reuters | **Refused** | — | robots.txt disallows all; notice forbids automated collection; 401 even to a browser UA |

## Takeaways
1. Every allowed site was solved by structured data; no CSS selectors were needed.
2. The useful AI work is **investigation** (finding the data source, mapping fields), not writing selectors.
3. Validation must check that links and images really work and that dates match the page.
4. "Empty" must be a separate status from "broken".
5. Never trust prior assumptions about a site; check live.
6. All allowed sites accepted our own User-Agent; no disguise needed.
7. The robots check must run **first**: it stops forbidden sites before any AI cost.
8. Title comparisons must HTML-unescape first (`&quot;`) and use `og:title` or `<h1>`.
9. Feeds may lack images; optionally fill them from each article's `og:image`.
10. Every source answered in under 1 s; polling cost is negligible.
