# Story matching (cross-source deduplication)

> Status: **specification** (2026-10-18). Backend only; how clusters are shown is decided later
> with the UI. Data model and general rules: [architecture.md](architecture.md#data-model-multi-tenant-and-wilaya-aware).

## Goal
Know, in the backend, which articles from **different sources** report **the same event**: e.g.
APS, El Hayat and Anadolu all publishing the President's decree of today, or the same earthquake in
Médéa, in Arabic or French.

- **Same event, not same topic.** "Council of Ministers meeting of 12 October" and "Council of
  Ministers meeting of 19 October" are different events. Two road accidents in two wilayas are
  different events. Only same-event pairs are grouped (`membership = duplicate`). Follow-ups and
  same-topic stories (`related`) are reserved for later and not produced in v1.
- **Precision over recall.** A wrong merge can hide a story from a journalist. A missed merge only
  shows one story twice. When unsure, keep articles apart and record a review candidate.
- **Cross-language.** The same event in Arabic and French must match. The current catalog is
  Arabic only (2026-10-19), so this applies once French sources are added; the design keeps it.
- **Fast.** Matching runs right after an article is stored, so alerts can know "already reported
  by X" (alert rules are a later phase; the cluster must already exist when they run).
- **Nothing is lost.** Every source article stays stored with its own URL; clusters are reversible
  (see [architecture.md](architecture.md)).

Same-source repeats (several listings, tracking parameters) are already handled by
`(source_id, external_id)` and `canonical_url_key`, before story matching runs.

## Pipeline
Runs for each new article, and again when an article's title or lead changes (new `version`).

### 1. Normalize (for matching only; stored text is unchanged)
Computed from title and lead and stored in `articles.match_text`:
- NFC, lowercase, Arabic-Indic and Eastern Arabic digits → `0-9`.
- **Arabic:** remove diacritics (tashkeel) and tatweel; unify `أ إ آ ٱ → ا`, `ى → ي`, `ة → ه`,
  `ؤ → و`, `ئ → ي`.
- **French:** strip accents, unify apostrophes and quotes.
- Remove punctuation, source boilerplate (`- APS`, `| El Hayat`, `فيديو:`, `عاجل`,
  `Urgent`, `VIDEO`) from a per-source and global list, and stopwords (ar, fr).

### 2. Extract signals per article
- **Embedding** of `title + lead` from an embedding API: **Voyage AI `voyage-4`** (multilingual,
  incl. Arabic and French; 1024 dimensions; $0.06 per 1M tokens), called **through OpenRouter**
  (model `voyageai/voyage-4`, OpenAI-compatible `POST https://openrouter.ai/api/v1/embeddings`).
  At ~1,600 articles/day × ~150 tokens ≈ 5M tokens/month, that is ~$0.30/month. (Voyage's own
  200M free tokens apply only to a direct Voyage account, not through OpenRouter.) `input_type` is left unset on both sides (symmetric comparison). Arabic and
  French texts about the same event land close together. Stored in pgvector.
  - Chosen over `voyage-4-lite` ($0.02) and OpenAI `text-embedding-3-small` ($0.02) because the
    hardest case is ar ↔ fr and precision matters more than a few cents; `voyage-4-lite` is not
    described as multilingual.
  - Only title and lead are sent (public on the source sites, never the body). The API key is
    `OPENROUTER_API_KEY` (model and base URL also from env: `EMBEDDING_MODEL`,
    `EMBEDDING_BASE_URL`); requests are batched (up to 128 texts) and retried with backoff.
  - **If the API is down**, the article is stored and ingested normally with
    `embedding_status = pending`; the worker retries and runs matching once the embedding
    exists. Matching is delayed, never skipped.
  - The embedder sits behind one interface (`embed(texts) -> vectors`) so the provider can change;
    changing it means re-embedding all open-window articles and re-tuning thresholds.
- **Key tokens:** normalized title tokens without stopwords (for same-language lexical overlap).
- **Numbers:** counts, amounts and dates found in title/lead (`15 قتيلا`, `3,5 milliards`,
  `12 أكتوبر`). Matching numbers are strong evidence; conflicting numbers of the same kind
  are evidence *against* (two different accidents).
- **Places:** wilayas and communes found with a gazetteer built from the `wilayas` table
  (`name_ar`, `name_fr`, common spellings), plus countries and capitals.
- **Named entities (v1, cheap):** a curated list of officials and institutions (President, Prime
  Minister, ministries, Sonatrach, ANP...) in ar and fr, linked to one ID so `تبون` and `Tebboune`
  match. A real NER model can replace this later if the list is not enough.
- **Time:** `published_at` (and its confidence), else `first_seen_at`.

### 3. Find candidates (blocking)
Compare only with articles that could plausibly match:
- other sources only (same-source repeats are handled before matching);
- published within **±36 h** (configurable; ±72 h for sources with low date confidence);
- top **20** nearest by embedding (pgvector HNSW index), plus same-language articles sharing at
  least two rare key tokens (catches near-identical agency wires the embedding might rank lower).

### 4. Score each pair
Signals, all stored in `dedup_candidates.signals` so every decision is explainable:

| Signal | Effect |
|---|---|
| Embedding cosine similarity (title + lead) | main signal |
| Lexical title overlap (same language only) | strong when very high (copied agency wire) |
| Shared numbers / conflicting numbers | strong + / strong − |
| Shared places / conflicting wilayas | + / − |
| Shared entities | + |
| Time gap | the larger, the weaker |
| Section (both "sport", one "sport" one "economy") | weak + / weak − |

v1 combines them with hand-set weights into a `score` in 0–1. Once enough labelled pairs exist,
the weights are fitted (logistic regression) on the evaluation set below.

Grouping rule (v1, configurable in `story_matching_config`):
- **Automatic group:** embedding cosine similarity of title + lead **≥ 0.90** **and** no hard
  conflict (different numbers of the same kind, different wilayas for a local event, different
  event dates, different named counterpart such as another country or ambassador). Exact matches
  (same canonical URL across sources, or identical normalized title and lead) also group.
  The article joins the cluster with `status = automatic`.
- **Review:** `0.85 ≤ cosine < 0.90`, or `≥ 0.90` with a hard conflict → a `pending` row in
  `dedup_candidates`; the articles stay apart until the review workflow (admin UI, later) decides.
- Below 0.85 → nothing stored.

Wilaya conflicts come from places found in the **text**, never from the sources' wilayas: a
Sétif local site and a `00` National source reporting the same Sétif event do not conflict.

The other signals (lexical overlap, shared numbers/places/entities, time) are stored with every
decision and used as conflict checks; they do not lower the 0.90 bar in v1.

Cosine 0.90 is **not** "90 % identical": each model has its own score range (unrelated news can
already score well above 0.5). Both values (0.90, 0.85) are initial settings chosen on 2026-10-18
and are checked for `voyage-4` with the calibration below. If unsure, the
evaluation moves the automatic threshold **up**, not down (precision over recall). Changes are
recorded in [decisions.md](decisions.md).

### 5. Assign to a cluster
A cluster is the event; an article is compared with the cluster, not only with one article:
- The article's cluster score = the **average of its best two** member scores (one member for a
  cluster of one). This avoids chaining (A≈B, B≈C, but A≉C).
- Only **open** clusters are considered: a cluster closes `cluster_window` (default 72 h) after
  its last member joined. A story that comes back a week later starts a new cluster (it may become
  `related` later).
- If the best match is an article with no cluster yet, a new cluster is created with both.
- If the article strongly matches **two** clusters, it joins the best one and a cluster-merge
  candidate is recorded; clusters are never merged automatically.
- The representative article is recomputed (rule in [architecture.md](architecture.md)).

When an article's title changes, its matches are re-scored; if it no longer matches its cluster,
it leaves only through a recorded split (never silently).

## Calibration and evaluation
**v1 (2026-10-19): no hand-labelled set.** Thresholds are set by judgement: automatic at cosine
**≥ 0.90** with no hard conflict, review at 0.85–0.90. Precision is protected by the conflict
checks, by never merging clusters automatically, and by every grouping being reversible.

**Calibration check (M8, no labelling needed):** because 0.90 means different things for
different models, before automatic grouping is switched on we measure `voyage-4` scores on real
fetched articles:
- *noise floor:* pairs from different days and different topics;
- *lookalikes:* same-topic pairs found automatically (same section, same entity, different days);
- *copies:* the same agency wire on two sites.

If lookalikes regularly score ≥ 0.90, the automatic threshold is **raised** (never lowered for
recall) until they fall below it; the chosen value and the score distribution are recorded in
[decisions.md](decisions.md). Pairs encountered along the way are kept in
`tests/fixtures/story_matching/pairs.jsonl` (both articles, label, note) as regression tests.

**Later, labelled evaluation:** a set of ≥ 300 pairs reviewed by a journalist (cross-language
pairs once French sources exist, hard negatives such as recurring meetings, the same incident type
in two wilayas, the same minister on two visits) to measure precision and recall properly. Re-run
when the model, weights, normalization or blocking change.

## Data model additions
Added to [architecture.md](architecture.md):
- `articles.match_text` (normalized title + lead) and `articles.match_signals jsonb` (numbers,
  places, entities).
- `articles.embedding_status[pending|done|failed]`.
- `article_embeddings(article_id, model, embedding vector(1024), created_at)`, primary key
  `(article_id, model)`, HNSW index; switching model means re-embedding, not altering rows.
- `story_clusters.first_published_at`, `last_member_at`, `closed_at` (for the open window).
- `dedup_candidates.kind[article|cluster_merge]` and `scorer_version` (which weights/thresholds
  produced the score).
- `story_matching_config` (thresholds, windows, weights, version), changes audited.

## Not in v1
- Displaying clusters (feed modes, story page): decided with the UI.
- `related` membership (follow-ups, same topic), topic clustering, AI classification.
- LLM judgement of uncertain pairs. Possible later for `pending` candidates, following the
  "our tools gather evidence, the LLM only judges" rule.
- Matching on article body text: v1 uses title + lead only, which every source provides.
