\# Design brief: Sabq (سبق), a news radar for newsrooms

## What the product is
Sabq watches Algerian news and official sources (news agencies, the Presidency, national and
regional press, many of which have no RSS) and shows journalists every new article within a
minute or two of publication, in one live stream. It is a professional monitoring tool that
journalists keep open all day on a desktop monitor, not a news site for the public. Each
newsroom (organisation) sees only the sources and wilayas (Algerian provinces) it subscribes to.

Sabq never shows full article text. Each article shows only its title, lead (first paragraph),
image and a link to the original on the source's site. Reading the full article always means
opening the original.

## Users
Journalists and editors in Algerian newsrooms. Roles: owner, admin, editor, viewer. Only owners
and admins see the Team screen. Their job is to spot news first ("سبق" means scoop / being
first), check who else is reporting it, and open the original.

## Design direction
- Calm, dense, fast to scan. Think a professional monitoring tool (news wire terminal, Linear,
  Slack), not a magazine. Information density beats decoration. No hero sections, no marketing.
- Desktop-first (1440 px and 1920 px monitors left open all day); fully usable on mobile (390 px).
- Light and dark themes, both first-class (dark matters for all-day use).
- **Main brand colour: yellow**, used for the brand and live activity (logo, live dot,
  new-articles pill, primary buttons, selected filters). Keep it restrained against neutral
  greys so it stays a signal, not a background.
  - Light theme: yellow works as a fill with dark text on it. Never use yellow text or thin
    yellow lines on white (unreadable); use a deeper amber/ochre shade of the same yellow for
    links and text accents.
  - Dark theme: the bright yellow can be used directly on near-black surfaces.
  - Check WCAG AA contrast for every text/background pair.
- Status colours (ok / delayed / stopped) must not be confused with the brand yellow: use
  green for ok, **orange** (not yellow) for delayed, red for stopped. Always pair them with an
  icon or label, so they don't rely on colour alone, and make them work in both themes.
- Typography: an Arabic typeface designed for screens (e.g. IBM Plex Sans Arabic or Noto Sans
  Arabic) paired with a matching Latin face for French. Headlines must be legible at a glance in
  both scripts. Tabular numerals for times and counts.

## Language and direction (important)
- Interface languages: Arabic (default, RTL) and French (LTR), switchable from the user menu.
  The whole layout mirrors with the language.
- Article content comes in both Arabic and French regardless of the interface language. A
  French article card inside the Arabic interface must render its title and lead LTR, while the
  card's frame, metadata and chips stay in the interface direction. Show this mix in the mocks.
- Times are Algiers time. Relative ("منذ 3 د" / "il y a 3 min") with the exact time on hover.

## Screens to design

### 1. Authentication (4 small screens)
Centred card on a quiet background, Sabq logo above.
- Login: email, password, "forgot password?" link.
- Accept invite: shows the organisation name the user was invited to, asks for display name and
  a new password.
- Forgot password: email field, then a "check your email" confirmation state.
- Reset password: new password + confirm.
Include error states (wrong password, expired link, too many attempts: try again later).

### 2. Radar (home): the main screen, design this most carefully
Layout (RTL shown; mirrored in French):
- **Top bar:** Sabq logo · tabs **"المستجدات" (Stream)** and **"القصص" (Stories)** · search
  box (searches titles and leads) · **live indicator** (a small pulsing dot + "مباشر" when the
  live connection is up; "جارٍ إعادة الاتصال…" when it drops, with a small "تحديث" (reload)
  link that only appears then) · user menu (name, organisation, language switch, theme, logout).
  Side navigation or top-bar links to: Radar, Sources, Team (owners/admins only), Account.
- **Filter rail** (on the right in RTL, collapsible):
  - **Wilayas:** only the organisation's granted wilayas, shown as code + name ("05 باتنة",
    "17 الجلفة", "19 سطيف", "00 وطني" for national), multi-select with counts.
  - **Sources:** the organisation's sources with search inside the list, multi-select.
  - Active filters appear as removable chips above the stream, with "clear all".
- **Stream** (centre): newest first, infinite scroll. Each **article card**:
  - source name (+ small language tag AR/FR) · relative time
  - **title**: the most prominent element
  - lead, clamped to 2 lines
  - thumbnail on the leading side when the article has an image; cards without an image must
    still look complete (many sources have none)
  - wilaya chips
  - an **"معدَّل" (edited)** marker when the source changed the article after publishing
  - a subtle marker when the publication time is estimated rather than given by the source
  - actions: open detail (click the card), "فتح الأصل" (open original, new tab)
- **Story grouping in the stream:** when several sources report the same event, show one
  card for the first/representative article with a row "+3 مصادر أخرى" (+3 other sources)
  showing the other source names. Clicking it expands in place to compact rows (source,
  time, title) for each other article. Collapse again.
- **New articles while reading:** the list never jumps. New arrivals collect in a floating
  pill at the top of the stream: "5 مقالات جديدة ↑". Clicking it scrolls to the top and
  reveals them, briefly highlighted. Design the burst case too: one regional daily uploads
  its whole edition (~60 articles) at once around midnight, so show "60 مقالًا جديدًا ↑",
  ideally with a hint of which source they came from.

### 3. Stories tab
A list of stories: events covered by several sources. Each story row:
- the representative headline
- the number of sources and their names/logos
- the time span: the first report and the latest update ("آخر تحديث منذ 12 د")
- language mix (e.g. 2 AR · 1 FR)
- wilaya chips
- a marker showing whether the story is still developing or closed

Clicking a story expands it, or opens the drawer, showing every article in it in time order:
source, time, title and lead. Same filters and search as the stream.

### 4. Article detail: side drawer
Opens over the stream from the leading side, so the reader keeps their place (full screen on
mobile).
- large image if any
- title and full lead
- source with its language
- author and section when known
- wilaya chips
- **published at** vs **first seen by Sabq** (both exact times, the gap shown small,
  e.g. "رُصد بعد 1 د")
- edited marker with the edit count when edited
- **"Same story" list:** other sources' articles about this event (source, time, title),
  each opening its own detail
- a large primary **"فتح المقال الأصلي"** (open original article) button

**There is no body text anywhere.** Don't design a reading view.

### 5. Sources
- A table/list of the organisation's subscribed sources. For each:
  - name and language
  - type (agency, official, national press, regional press)
  - wilayas
  - a friendly status: يعمل (working) / متأخر (delayed) / متوقف (stopped)
  - last checked ("آخر فحص منذ 40 ث")
  - usual rhythm ("~20 مقالًا يوميًا", or "نشرة يومية حوالي منتصف الليل" for a daily edition)

  The rhythm shows that a quiet source isn't broken.
- **"اطلب مصدرًا" (Request a source):** a form with the URL and an optional note, for asking
  the Sabq team to add a site.
- **"طلباتي" (My requests):** each with its URL, date and status (pending / added /
  declined), and the reason when declined.

### 6. Team (owner/admin only)
- Invite a user: email, display name, role (admin / editor / viewer), with a role
  explanation.
- Show the sent-invitation state.

### 7. Account
- Display name, email, role, organisation
- language and theme preferences
- logout

## States to show
- loading skeletons for the stream
- empty stream (no articles match the filters, with a "clear filters" action)
- the stream reconnecting
- a no-results search
- a source with "stopped" status
- the first-time state with very few articles

## Sample content to use

**Sources (our real catalog):**
- APS (وكالة الأنباء الجزائرية): national, AR
- رئاسة الجمهورية (the Presidency): national, AR
- الأناضول (Anadolu): national, AR
- الحياة (El Hayat): national, AR
- الأوراس نيوز (Awras News): 05 باتنة, AR
- الهضاب (El Hidhab): 05 باتنة, AR
- الجلفة إنفو (Djelfa Info): 17 الجلفة, AR
- سطيف وان (Setif One): 19 سطيف, AR

Add one or two French-language sources for the mixed-direction mocks.

**Headlines:** write realistic, neutral Algerian news headlines in Arabic and a few in French:
- an official decree
- weather alerts for several wilayas
- a sports result
- a regional infrastructure project

Make one story shared by 4 sources, two of them French.

## Deliverables
Desktop (1440 px) and mobile (390 px) for:
- the Radar stream, in Arabic and in French, with a mixed-language example
- the expanded story card
- the Stories tab
- the article drawer
- Sources
- Team
- Account
- the auth screens

Show both dark and light themes for the Radar.

Also provide the component set:
- the article card in all its variants (image or none, edited, estimated time, story group)
- chips
- status badges
- the live indicator in both states
- the new-articles pill
- the filter rail

Mobile:
- the filter rail becomes a bottom sheet opened from a filter button
- the tabs stay at the top
- navigation moves to a bottom bar
