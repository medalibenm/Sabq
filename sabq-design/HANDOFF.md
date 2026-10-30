# Sabq (سبق) — design handoff for implementation

This folder is the design for Sabq, a live news radar for Algerian newsrooms. It was built as a design canvas; every screen is in `design/` as a `.dc.html` file (HTML + inline styles + a small `renderVals()` JS class). Treat those files as the **visual and behavioural reference**, not as production code: re-implement them in the project's own stack and component library.

## How to read the `.dc.html` files
- Markup between `<x-dc>` … `</x-dc>` is the layout. `{{name}}` holes are filled by `renderVals()` in the `<script type="text/x-dc">` block at the bottom.
- `<sc-for list="{{items}}" as="it">` = a loop, `<sc-if value="{{cond}}">` = a conditional, `<dc-import name="X" prop="…">` = renders component `X.dc.html` with props (kebab-case attributes → camelCase props).
- Each file has `TK` (theme tokens, dark/light), `FONT`, and `LBL` (AR/FR strings). Sample data lives in the script (`RAW`, `STORIES`, `ROWS`…).
- `canvas.json` lists every artboard with its size and title.

## Files
| File | What it is |
|---|---|
| `Main.dc.html` | **Radar screen** (stream). Props: `theme` dark/light, `ui` ar/fr, `view` (live, filtered, expanded, drawer, menu, reconnecting, burst, loading, empty, noresults, firsttime). Holds filtering, search, pill reveal, story expand, drawer state. |
| `ArticleCard.dc.html` | Article card + story group (collapsed/expanded rows). |
| `TopBar.dc.html` | Logo, Stream/Stories tabs, search, live indicator (up/down), user menu (language, theme, account, logout). |
| `SideNav.dc.html` | Radar / Sources / Team (owner+admin only) / Account. |
| `FilterRail.dc.html` | Sources (first) + wilayas multi-select with counts, source search and a "show more" toggle per section (5 sources / 3 wilayas visible, selected items always shown); `variant` rail or mobile `sheet`; collapsible. |
| `Drawer.dc.html` | Article detail drawer (desktop side drawer / mobile full screen). |
| `Stories.dc.html` | Stories tab: story rows, expand to timeline. |
| `Sources.dc.html` | Sources table with status + rhythm, request form, "my requests". |
| `Team.dc.html` | Invite form with role explanations, member list, sent state (`sent` prop). |
| `Account.dc.html` | Profile, language, theme, logout. |
| `Auth.dc.html` | Login, wrong password, rate-limited, accept invite, forgot, check email, reset, expired link (`variant`), `frame` page/card. |
| `Mobile.dc.html` | 390 px shell: top tabs, bottom nav, filter bottom sheet, full-screen drawer; `screen` prop. |
| `Components.dc.html` | Component set + colour tokens with contrast ratios. |
| Other `Radar-*`, `M-*`, `*-FR`, `Auth-*` files | Thin wrappers that render the above with specific props (theme/lang/state variants). |

## Design tokens
Fonts: **IBM Plex Sans Arabic** (Arabic UI/content) + **IBM Plex Sans** (French), weights 400/500/600/700, `font-variant-numeric: tabular-nums` everywhere times/counts appear.

| Token | Dark | Light |
|---|---|---|
| bg | #0F1012 | #F3F3F0 |
| panel (bars, rail) | #141619 | #FAFAF8 |
| card | #191B1F | #FFFFFF |
| line / line2 | #272A30 / #363A41 | #E2E2DD / #CFCFC8 |
| text / text2 / text3 | #EDEDEF / #A9ACB4 / #8A8E97 | #16171A / #4B4D55 / #686B73 |
| chip | #23262B | #EFEFEB |
| brand yellow (fill) | #FFD23F | #FFD23F |
| text on yellow | #1A1600 | #1A1600 |
| accent text / links | #FFD23F | **#835800** (never yellow text on light) |
| accent soft (selected bg) | rgba(255,210,63,.14) | #FFF3C4 |
| ok | #4ADE80 | #1C7A3B |
| delayed (orange, not yellow) | #FB923C | #B54E0B |
| stopped | #F87171 | #C1272D |

All text/background pairs checked for WCAG AA (lowest 4.5:1). Radii: cards 10px, inputs/buttons 8px, chips pill. Yellow is only for brand, live dot, new-articles pill, primary buttons, selected filters. Status always = colour + icon + label.

## Layout
- Desktop: top bar 56px · side nav 72px · filter rail 280px (collapsible to 52px) · stream column max-width 880px centred. Drawer 560px opens from the **leading** side (right in AR, left in FR) over a scrim.
- Mobile 390px: header + tabs at top, filter button opens bottom sheet, bottom nav 64px, drawer full screen.
- Use **logical CSS properties** (`margin-inline-start`, `inset-inline-start`, `text-align: start`) so the whole layout mirrors with `dir`.

## Bidirectional content (important)
Interface direction comes from the UI language (AR = rtl, FR = ltr). Each article's **title and lead get their own `dir` + `lang` + font from the article's language**, while the card frame, metadata and chips follow the interface. Source names use `<bdi>`. Times: relative ("منذ 3 د" / "il y a 3 min") with exact Algiers time in `title` on hover; estimated times get "≈" + dotted underline + "تقديري".

## Behaviour to implement
- Stream newest first, infinite scroll. **New articles never shift the list**: they collect in the floating yellow pill ("5 مقالات جديدة ↑"); clicking scrolls to top and reveals them with a soft yellow highlight. Burst case shows count + dominant source ("60 مقالًا جديدًا · 58 منها من الأوراس نيوز").
- Story grouping: one representative card + "+3 مصادر أخرى" row; expands in place to compact rows (source, lang tag, time, title, open-original).
- Filters: wilaya + source multi-select; active filters as removable chips above the stream with "clear all". Search covers titles and leads only.
- Live indicator: pulsing dot + "مباشر"; on disconnect spinner + "جارٍ إعادة الاتصال…" + "تحديث" link (only then).
- Drawer: image, title, full lead, source+lang, author/section when known, wilayas, published vs first-seen (with gap), edit count, same-story list, big "فتح المقال الأصلي". **No article body anywhere.**
- Team page visible to owner/admin only.
- States to support: loading skeletons, empty (filters → "مسح الفلاتر"), no search results, reconnecting, stopped source, first-time few articles.

## Assumptions made in the design (confirm with product)
- Sample content (headlines, the newsroom "يومية الأفق", users, French sources El Moudjahid and L'Expression, request URLs) is fictional.
- Invite links expire after 7 days; reset links after 1 hour, single use; lockout 15 minutes after too many attempts.
- Editors can request sources; viewers are read-only.
- Image and source-logo slots are grey placeholders.
