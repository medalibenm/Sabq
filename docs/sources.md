# Source catalog

One row per source **per language**. "Verified" = probed and working in the PoC (2026-10-17). Everything else is a **candidate**: it must go through [adding-sources.md](adding-sources.md) before it enters the catalog.

## Verified

| Slug | Name | Wilaya | Method | Endpoint | Poll | Robots | Notes |
|---|---|---|---|---|---|---|---|
| `aps-ar` | APS (العربية) | 00 National/International | embedded data (Next.js `self.__next_f`) | `/`, `/algerie/actualite-nationale`, `/presidence-news` | 60 s | allows all | UTC `publish_date`; 8-char ID in URL; images under `/api/image/`; skip dossier/infographie/video; config `catalog/aps-ar.yaml` (re-checked 2026-10-21) |
| `mouradia-ar` | رئاسة الجمهورية (Presidency) | 00 National/International | internal JSON API (Strapi) | `backend.el-mouradia.dz/article-ars/published` | 5 min | allows all | links `/ar/{president\|presidency}/{_id}`; SPA returns 200 for any URL; `mouradia-fr` is **empty**; config `catalog/mouradia-ar.yaml` (re-checked 2026-10-21) |
| `elhayat-ar` | El Hayat | 00 National/International | WordPress REST API | `/wp-json/wp/v2/posts` | 2 min | allows all | `/feed/` times out; images from Yoast `og_image`; config `catalog/elhayat-ar.yaml` (re-checked 2026-10-21) |
| `awras-ar` | الأوراس نيوز (Awras News) | 05 باتنة | WordPress REST API (`_embed` for image and section) | `/wp-json/wp/v2/posts?per_page=100` | 30 min | allows all (except `/wp-admin/`), checked 2026-10-19 | Daily: uploads the edition at once, 60–73 posts at 23:00–23:12 UTC; `/feed/` holds only 25 so would miss most; API slow (~8.5 s); site tz Africa/Algiers, `date_gmt` correct; images 302 → `cdn.elauresnews.dz`. Config `catalog/awras-ar.yaml` |
| `elhidhab-ar` | الهضاب (El Hidhab) | 05 باتنة | WordPress REST API | `/wp-json/wp/v2/posts?per_page=20` | 60 min | empty robots.txt (no restrictions), checked 2026-10-19 | ~0.6 posts/day, irregular; content mostly national news and weather, not Batna; feed says `en-US` but content is Arabic; WP timezone unset, dates read as Africa/Algiers (to confirm). Config `catalog/elhidhab-ar.yaml` |
| `djelfainfo-ar` | الجلفة إنفو (Djelfa Info) | 17 الجلفة | official RSS (custom CMS) | `/ar/rss.php` | 15 min | allows all except `/ar/inc/`, `/ar/admin/`, `/ar/uploads/`, checked 2026-10-21 | 2–21 posts/day; feed holds the latest 10, title = description, so the lead comes from the article page (`og:description`, JSON-LD `NewsArticle`); `pubDate` ISO 8601 in true UTC (page shows +01:00); ID from URL `/(\d+).html`; image = `enclosure` on `cdn.djelfainfo.dz`; feed says `en-us` but is Arabic. Mostly national news (`news/algerie`); Djelfa stories are in `news/djelfa` (useful for section-based wilayas later). An article can enter the feed after its `pubDate` (152487, dated 14:18 UTC, was still 404 at 15:37 UTC), so detection delays can look long. `/ar/sitemap.xml` lists unpublished articles too (302 → 404.php): not used. Config `catalog/djelfainfo-ar.yaml` |
| `setifone-ar` | سطيف وان (Setif One) | 19 سطيف | WordPress REST API (`_embed`) | `/wp-json/wp/v2/posts?per_page=20` | 60 min | allows all except `/wp-admin/`, checked 2026-10-21 | 1–2 posts/day; WordPress `gmt_offset` 1, so `date_gmt` is true UTC; images and sections via `_embed`; mostly national news (أخبار الوطن), local stories under قضايا محلية. Config `catalog/setifone-ar.yaml` |
| `aa-ar` | Anadolu Agency (Arabic) | 00 National/International | official RSS | `/ar/rss/default?cat=guncel` | 2 min | allows all except `/api/` | dates +03:00 → UTC; no images in feed; items not in date order; config `catalog/aa-ar.yaml` (re-checked 2026-10-21) |
| `seybouse-fr` | Seybouse Times | 23 عنابة | WordPress REST API (`_embed`) | `/wp-json/wp/v2/posts?per_page=30` | 30 min | allows all, checked 2026-10-30 | ~10 posts/day; true UTC; `PDF` section excluded (daily edition, not articles). Config `catalog/seybouse-fr.yaml` |
| `reflexion-fr` | La Réflexion | 27 مستغانم | WordPress REST API (`_embed`) | `/wp-json/wp/v2/posts?per_page=20` | 60 min | allows all except `/wp-admin/`, checked 2026-10-30 | ~4 posts/day; page says `lang=en`, content is French; WP timezone unset, dates read as Africa/Algiers (to confirm). One dropped connection in validation, then 3 clean runs. Config `catalog/reflexion-fr.yaml` |
| `cherchellnews-ar` | شرشال نيوز (Cherchell News) | 42 تيبازة | WordPress REST API (`_embed`) | `/wp-json/wp/v2/posts?per_page=20` | 60 min | allows all except `/wp-admin/`, `Crawl-delay: 10`, checked 2026-10-30 | ~3 posts/day; true UTC. Config `catalog/cherchellnews-ar.yaml` |
| `elchark-ar` | الشرق اليوم (El Chark El Youm) | 00 National/International | WordPress REST API (`_embed`) | `/wp-json/wp/v2/posts?per_page=20` | 30 min | allows all, checked 2026-10-30 | ~5 posts/day; `/feed/` drops the connection; WP timezone unset, dates read as Africa/Algiers (to confirm). Config `catalog/elchark-ar.yaml` |
| `quotidienconstantine-fr` | Le Quotidien de Constantine | 25 قسنطينة | WordPress REST API by `rest_route` (`_embed`) | `/?rest_route=/wp/v2/posts&per_page=20` | 60 min | no robots.txt (404), checked 2026-10-30 | 1–4 posts/day; true UTC; no pretty permalinks, links are `?p=ID`; RSS at `?feed=rss2` has no images. Config `catalog/quotidienconstantine-fr.yaml` |
| `asdaa-ar` | أصداء الغرب (Asdaa Algharb) | 31 وهران | WordPress REST API by `rest_route` (`_embed`) | `/?rest_route=/wp/v2/posts&per_page=20` | 60 min | no robots.txt (404), checked 2026-10-30 | ~2 posts/day; true UTC; `/feed/` drops the connection, links are `?p=ID`. Config `catalog/asdaa-ar.yaml` |
| `eldjoumhouria-ar` | الجمهورية (El Djoumhouria) | 31 وهران | official RSS | `www.eldjoumhouria.dz/feed/` | 15 min | no robots.txt (404), checked 2026-10-30 | ~13 posts/day, feed of 40; dates +0100; no images in the feed, so `og:image` from article pages; summary starts with the section. Config `catalog/eldjoumhouria-ar.yaml` |
| `quotidienoran-fr` | Le Quotidien d'Oran | 31 وهران | official RSS | `/rss.xml` | 30 min | allows all except `/admin/`, `/manage-portal/`, most of `/api/`, checked 2026-10-30 | Daily edition, ~30 posts/day, feed of 100, ~10 s; dates are the edition's (08:00 or 09:00 UTC), not each article's; feed has full text, kept out of fixtures. Config `catalog/quotidienoran-fr.yaml` |
| `elkhabar-ar` | الخبر | 00 National/International | official RSS | `/feed/` | 5 min | disallows `/api`, `/captcha`, `/login`, `*/view`, `*/comments`, checked 2026-10-31 | Feed: 5 newest + 5 columns + 5 videos (excluded). Date `13:40 \| 31-10-2026`, Algiers time (14:57 seen at 14:04 UTC). Image and lead inside the summary. Config `catalog/elkhabar-ar.yaml` |
| `elkhabar-fr` | El Khabar | 00 National/International | official RSS | `/fr/feed/` | 5 min | as `elkhabar-ar`, checked 2026-10-31 | 10 items, 5 of them columns, some old. Same format. Config `catalog/elkhabar-fr.yaml` |
| `echorouk-ar` | الشروق | 00 National/International | official RSS | `/feed/` | 5 min | disallows `/wp-admin/` only, checked 2026-10-31 | 10 items, about 2 hours; Cloudflare; true UTC; WP API off; image in `content`. Config `catalog/echorouk-ar.yaml` |
| `ennahar-ar` | النهار | 00 National/International | official RSS | `/feed/` | 5 min | allows all, checked 2026-10-31 | 10 items, about 3 hours; Cloudflare; true UTC; WP API off; feed has full text, kept out of fixtures. Config `catalog/ennahar-ar.yaml` |
| `elwatan-fr` | El Watan | 00 National/International | WP API | `/wp-json/wp/v2/posts` | 15 min | allows all, checked 2026-10-31 | elwatan.dz, not elwatan-dz.com. About 40 posts land around 09:00 UTC; 1 MB per poll; `/feed/` drops the connection; PDF category 250 excluded. Config `catalog/elwatan-fr.yaml` |
| `elmoudjahid-fr` | El Moudjahid | 00 National/International | official RSS | `/fr/feed` | 5 min | disallows only `/*index.php*`, checked 2026-10-31 | Same CMS and date format as El Khabar, Algiers time (14:19 seen at 13:55 UTC). 20 items: 5 newest + 5 of each of 3 rubrics, photos excluded. Images on elmoudjahid.com. Config `catalog/elmoudjahid-fr.yaml` |

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
| An-Nasr (annasronline.com) | 25 قسنطينة | 2026-10-30 | robots.txt allows articles (disallows Joomla system paths). Joomla behind Cloudflare: the feeds (`?format=feed&type=rss`, also per category) answer 520 to our bot, no sitemap, no JSON-LD. Pages are public: `/section/sub/<id>-<slug>` with `og:title`, `og:description`, `og:image`. Needs the HTML extractor. |
| Le Provincial (leprovincial.dz) | 23 عنابة | 2026-10-31 | 508 on 2026-10-30, back on 2026-10-31. robots.txt allows all. WordPress in French; `/feed/` and the WP API work, 11,348 posts, true UTC. Ready for a config. Watch the hosting limit. |

## Inactive
Reachable and allowed, but no longer publishing. Not in the catalog; recheck now and then.

| Site | Wilaya | Checked | Finding |
|---|---|---|---|
| La Dépêche de Kabylie (depechedekabylie.com) | 15 تيزي وزو | 2026-10-21 | robots.txt allows all with `Crawl-delay: 10`. WordPress; `/feed/` returns the homepage (feed disabled), but `/wp-json/wp/v2/posts` works (201,977 posts). Newest post is **2021-06-28**; the homepage still shows 2020 articles. The only recent activity is old posts edited on 2026-03-07 (maintenance). If it restarts: WP API, ≥ 10 s between requests. |
| L'Echo d'Oran (echodoran.com) | 31 وهران | 2026-10-30 | robots.txt allows all with `Crawl-delay: 60`. Static HTML pages, no feed or API. The homepage still shows the edition of 22 June 2025. If it restarts: needs the HTML extractor. |

## Probed candidates
Probed 2026-10-31 from an Algerian connection (Telecom Algeria), with our own User-Agent, robots.txt
read first. None has a config yet. Most may refuse a server abroad, so re-test from the server.

**Ready for a config:** structured data, allowed by robots.txt, publishing now.

| Name | URL | Language | Method | Notes |
|---|---|---|---|---|
| APN | apn.dz | ar, fr (es too) | RSS `/API/rss?lang=ar` | 15 items; French titles contain `<p>`; no images |
| Education ministry | education.gov.dz | ar | WP API | 430 posts; a few a week |
| ANIE | ina-elections.dz | ar | WP API | 494 posts; excerpts are page-builder code, the lead must come from the feed or page |
| Constitutional Court | cour-constitutionnelle.dz | ar (fr to check) | WP API | 1,342 posts; excerpts are page-builder code; home page drops the connection |
| Bank of Algeria | bank-of-algeria.dz | fr | WP API | 1,159 posts, many are procurement notices: filter by category |
| Sonatrach | sonatrach.com | to check | WP, `/en/category/news/` | robots.txt answered 503 once, then the site worked; recheck robots, WP API not tested |

**Needs embedded data or an API found in the pages:**

| Name | URL | Finding |
|---|---|---|
| Foreign Affairs | mfa.gov.dz | Next.js, `__NEXT_DATA__`; `/announcements/...`; newest seen 8 Sept 2026 |
| Communication ministry | mcomm.gov.dz (old name redirects) | Next.js `__next_f`; `/ar/posts/<id>`; dated this week |

**Needs the HTML extractor:**

| Name | URL | Finding |
|---|---|---|
| Prime Minister | premier-ministre.gov.dz | No feed; `/ar/document/...` with dates, current. Government communiqués: high value |
| Council of the Nation | majliselouma.dz | No feed; `/ara/articles?categories=...` |
| EPTV | entv.dz | Drupal, no feed found; `/ar/news/...`, current |
| Defence | mdn.dz | Old PHP site, `/site_principal/sommaire/actualites/ar/actualites_ar.php` |
| Energy | energy.gov.dz | No feed found; numbered pages |
| Commerce | commerce.gov.dz | `/actualites/...`, mostly tender notices |

**Refused or blocked:**

| Name | URL | Finding |
|---|---|---|
| Interior | interieur.gov.dz | robots.txt allows, but `/ar/feed/` answered 403 to our bot. Stopped, not worked around |
| Anadolu (fr) | aa.com.tr/fr | Guessed feed categories 404, `/fr/rss/` timed out. Retry: `aa-ar` already works from the same site |

**Unavailable or unclear:**

| Name | URL | Finding |
|---|---|---|
| Finance | mf.gov.dz | robots.txt timed out twice, nothing fetched |
| Health | sante.gov.dz | WordPress, only 4 posts, newest October 2024. Effectively inactive there |
| TSA | tsa-algerie.dz (.com refuses connections) | `/feed/` drops the connection, API 404. Sitemap to try |
| Echaab | ech-chaab.com/new | WP API worked once (217,984 posts), then dropped the connection; `/feed/` timed out. Retry |
| Radio Algérienne | radioalgerie.dz | Home is a redirect stub; follow it |
| Journal officiel | joradp.dz | Old frameset; publishes PDFs, needs its own approach |

**Not probed:** APS in English (APS is followed in Arabic only, 2026-10-19). YouTube and Telegram
channels: need a decision and the channel list. Other agencies: none named yet.

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
| 23 عنابة | Le Provincial | https://leprovincial.dz/ (ready for a config, see Investigating) |
| 23 عنابة | Seybouse Times | https://seybousetimes.dz/ (verified, `seybouse-fr`) |
| 25 قسنطينة | An-Nasr | https://www.annasronline.com/ (investigating: needs HTML extractor) |
| 25 قسنطينة | Le Quotidien de Constantine | https://lequotidien-deconstantine.dz/ (verified, `quotidienconstantine-fr`) |
| 27 مستغانم | La Réflexion | https://www.reflexion.dz/ (verified, `reflexion-fr`) |
| 31 وهران | El Djoumhouria | https://eldjoumhouria.dz/ (verified, `eldjoumhouria-ar`) |
| 31 وهران | Le Quotidien d'Oran | https://lequotidien-oran.dz/ (verified, `quotidienoran-fr`) |
| 31 وهران | Asdaa Algharb | https://asdaalgharb.dz/ (verified, `asdaa-ar`) |
| 31 وهران | L'Echo d'Oran | https://www.echodoran.com/ (inactive since 2025, see above) |
| 42 تيبازة | Cherchell News | https://www.cherchellnews.dz/ (verified, `cherchellnews-ar`) |
| 00 National | El Chark El Youm | https://elcharkelyoum.dz/ (verified, `elchark-ar`) |
do  
`El Chark El Youm` covers the East region rather than one wilaya, so it is `00 National` for now.
Several of these sources publish in French; language is confirmed during investigation.

## To decide
- Languages: Arabic and French only, or English / Tamazight too?
- Tiers: which sources are `priority` (60 s), `normal` (2–5 min), `secondary` (15–60 min)?
