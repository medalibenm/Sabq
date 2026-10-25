# Source catalog

One row per source **per language**. "Verified" = probed and working in the PoC (2026-10-17). Everything else is a **candidate**: it must go through [adding-sources.md](adding-sources.md) before it enters the catalog.

## Verified

| Slug | Name | Wilaya | Method | Endpoint | Poll | Robots | Notes |
|---|---|---|---|---|---|---|---|
| `aps-ar` | APS (العربية) | 00 National | embedded data (Next.js `self.__next_f`) | `/`, `/algerie/actualite-nationale`, `/presidence-news` | 60 s | allows all | UTC `publish_date`; 8-char ID in URL; images under `/api/image/`; skip dossier/infographie/video; config `catalog/aps-ar.yaml` (re-checked 2026-10-21) |
| `mouradia-ar` | رئاسة الجمهورية (Presidency) | 00 National | internal JSON API (Strapi) | `backend.el-mouradia.dz/article-ars/published` | 5 min | allows all | links `/ar/{president\|presidency}/{_id}`; SPA returns 200 for any URL; `mouradia-fr` is **empty**; config `catalog/mouradia-ar.yaml` (re-checked 2026-10-21) |
| `elhayat-ar` | El Hayat | 00 National | WordPress REST API | `/wp-json/wp/v2/posts` | 2 min | allows all | `/feed/` times out; images from Yoast `og_image`; config `catalog/elhayat-ar.yaml` (re-checked 2026-10-21) |
| `awras-ar` | الأوراس نيوز (Awras News) | 05 باتنة | WordPress REST API (`_embed` for image and section) | `/wp-json/wp/v2/posts?per_page=100` | 30 min | allows all (except `/wp-admin/`), checked 2026-10-19 | Daily: uploads the edition at once, 60–73 posts at 23:00–23:12 UTC; `/feed/` holds only 25 so would miss most; API slow (~8.5 s); site tz Africa/Algiers, `date_gmt` correct; images 302 → `cdn.elauresnews.dz`. Config `catalog/awras-ar.yaml` |
| `elhidhab-ar` | الهضاب (El Hidhab) | 05 باتنة | WordPress REST API | `/wp-json/wp/v2/posts?per_page=20` | 60 min | empty robots.txt (no restrictions), checked 2026-10-19 | ~0.6 posts/day, irregular; content mostly national news and weather, not Batna; feed says `en-US` but content is Arabic; WP timezone unset, dates read as Africa/Algiers (to confirm). Config `catalog/elhidhab-ar.yaml` |
| `djelfainfo-ar` | الجلفة إنفو (Djelfa Info) | 17 الجلفة | official RSS (custom CMS) | `/ar/rss.php` | 15 min | allows all except `/ar/inc/`, `/ar/admin/`, `/ar/uploads/`, checked 2026-10-21 | 2–21 posts/day; feed holds the latest 10, title = description, so the lead comes from the article page (`og:description`, JSON-LD `NewsArticle`); `pubDate` ISO 8601 in true UTC (page shows +01:00); ID from URL `/(\d+).html`; image = `enclosure` on `cdn.djelfainfo.dz`; feed says `en-us` but is Arabic. Mostly national news (`news/algerie`); Djelfa stories are in `news/djelfa` (useful for section-based wilayas later). An article can enter the feed after its `pubDate` (152487, dated 14:18 UTC, was still 404 at 15:37 UTC), so detection delays can look long. `/ar/sitemap.xml` lists unpublished articles too (302 → 404.php): not used. Config `catalog/djelfainfo-ar.yaml` |
| `setifone-ar` | سطيف وان (Setif One) | 19 سطيف | WordPress REST API (`_embed`) | `/wp-json/wp/v2/posts?per_page=20` | 60 min | allows all except `/wp-admin/`, checked 2026-10-21 | 1–2 posts/day; WordPress `gmt_offset` 1, so `date_gmt` is true UTC; images and sections via `_embed`; mostly national news (أخبار الوطن), local stories under قضايا محلية. Config `catalog/setifone-ar.yaml` |
| `aa-ar` | Anadolu Agency (Arabic) | 00 National | official RSS | `/ar/rss/default?cat=guncel` | 2 min | allows all except `/api/` | dates +03:00 → UTC; no images in feed; items not in date order; config `catalog/aa-ar.yaml` (re-checked 2026-10-21) |

## Removed

| Slug | Removed | Reason |
|---|---|---|
| `aps-fr` | 2026-10-19 | Product decision: APS is followed in Arabic only. Config and fixtures from the PoC kept for reference. |
| `afp-corporate-fr` | 2026-10-19 | Product decision. The feed carried AFP's news about itself, not the wire. |

## Refused

| Site | Reason | Route |
|---|---|---|
| Reuters (reuters.com) | robots.txt `User-agent: *` / `Disallow: /`; notice forbids automated collection without written consent; 401 to any client | Licence (Reuters Connect) |

## Investigating

| Site | Wilaya | Checked | Finding |
|---|---|---|---|
| Sawt Setif (sawtsetif.dz, canonical sawtsetif.com) | 19 سطيف | 2026-10-21 | No robots.txt on either host (404 = allowed). Custom CMS ("DWM V4", Djidel Solutions): no feed, no sitemap, no JSON-LD, no API for articles. Articles at `/v/<id>/` (ids increase, ~4/day); the homepage and each article's "latest" block list `<a href="/v/<id>/"><span>DD-MM-YYYY</span><span>title</span></a>`; article pages carry schema.org microdata (`itemprop="headline"`, `datePublished` **date only**, `og:image` = `/api/file/<n>`). Needs the HTML (CSS selector) extractor, not built yet, and date-only handling (first-seen time, day checked). |

## Inactive
Reachable and allowed, but no longer publishing. Not in the catalog; recheck now and then.

| Site | Wilaya | Checked | Finding |
|---|---|---|---|
| La Dépêche de Kabylie (depechedekabylie.com) | 15 تيزي وزو | 2026-10-21 | robots.txt allows all with `Crawl-delay: 10`. WordPress; `/feed/` returns the homepage (feed disabled), but `/wp-json/wp/v2/posts` works (201,977 posts). Newest post is **2021-06-28**; the homepage still shows 2020 articles. The only recent activity is old posts edited on 2026-03-07 (maintenance). If it restarts: WP API, ≥ 10 s between requests. |

## Candidates to probe (unverified)
From general knowledge; URLs and availability to confirm.

| Category | Candidates |
|---|---|
| Presidency & government | Prime Minister's office · Official Journal (joradp.dz) |
| Parliament | National People's Assembly (apn.dz) · Council of the Nation (majliselouma.dz) |
| Ministries | Foreign Affairs · Interior · Defence (mdn.dz) · Finance · Energy & Mines · Commerce · Health · Education · Communication |
| Institutions | Constitutional Court · ANIE (elections) · Bank of Algeria · Sonatrach |
| Public media | APS (en?) · Radio Algérienne · EPTV · El Moudjahid · Echaab |
| National press | El Khabar · Echorouk · Ennahar · El Watan · TSA · (others) |
| International | Anadolu (fr?) · other agencies with official RSS |
| Social (official) | YouTube channels (public RSS) of the Presidency and ministries · public Telegram channels |

## Local candidates by wilaya (unverified)
Provided 2026-10-19. Each source is assigned the wilaya listed here (see
[architecture.md](architecture.md#wilaya-assignment)); a source with no wilaya is `00 National`.
Each must still go through [adding-sources.md](adding-sources.md) (live robots.txt check first).

| Wilaya | Name | URL |
|---|---|---|
| 15 تيزي وزو | La Dépêche de Kabylie | https://www.depechedekabylie.com (inactive since 2021, see above) |
| 17 الجلفة | Djelfa Info | https://djelfainfo.dz/ar/ (verified, `djelfainfo-ar`) |
| 19 سطيف | Sawt Setif | https://sawtsetif.dz/ (investigating: needs HTML extractor) |
| 19 سطيف | Setif One | https://setifone.dz/ (verified, `setifone-ar`) |
| 23 عنابة | Le Provincial | https://leprovincial.dz/ |
| 23 عنابة | Seybouse Times | https://seybousetimes.dz/ |
| 25 قسنطينة | An-Nasr | https://www.annasronline.com/ |
| 25 قسنطينة | Le Quotidien de Constantine | https://lequotidien-deconstantine.dz/ |
| 27 مستغانم | La Réflexion | https://www.reflexion.dz/ |
| 31 وهران | El Djoumhouria | https://eldjoumhouria.dz/ |
| 31 وهران | Le Quotidien d'Oran | https://lequotidien-oran.dz/ |
| 31 وهران | Asdaa Algharb | https://asdaalgharb.dz/ |
| 31 وهران | L'Echo d'Oran | https://www.echodoran.com/ |
| 42 تيبازة | Cherchell News | https://www.cherchellnews.dz/ |
| 00 National | El Chark El Youm | https://elcharkelyoum.dz/ |
do  
`El Chark El Youm` covers the East region rather than one wilaya, so it is `00 National` for now.
Several of these sources publish in French; language is confirmed during investigation.

## To decide
- Languages: Arabic and French only, or English / Tamazight too?
- Tiers: which sources are `priority` (60 s), `normal` (2–5 min), `secondary` (15–60 min)?
