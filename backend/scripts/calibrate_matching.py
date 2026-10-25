"""Calibration of story-matching scores on real articles (docs/story-matching.md, calibration).

Re-run when the embedding model, normalisation or thresholds change:

    cd backend && uv run --with numpy python scripts/calibrate_matching.py [--live] [--out DIR]

Corpus: every catalog source's saved fixtures, plus (with --live) its current listings fetched
through the polite fetcher. Every title + lead is embedded with the configured model (a few cents
at most), then every cross-source pair is scored and grouped:

  noise        published more than 48 h apart, no shared entity or wilaya: the floor
  lookalikes   more than 48 h apart but sharing an entity or a wilaya: same topic, other event
  near         within 36 h: where same-event pairs are; the top ones are listed to be judged

Writes DIR/pairs.json (all near pairs above 0.6 with titles, cosine, conflicts) and prints
percentiles. Nothing is written to the database.
"""

import argparse
import asyncio
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np

from sabq.catalog import read_catalog
from sabq.cli import DEFAULT_CATALOG, DEFAULT_FIXTURES
from sabq.extract.extractor import extract_listing, merge_listings
from sabq.fetch import Fetcher, FetchError
from sabq.matching.embed import OpenRouterEmbedder, embedding_text
from sabq.matching.signals import Gazetteer, conflicts, extract
from sabq.settings import Settings

SEED = DEFAULT_CATALOG.parent / "backend/alembic/versions/20261021_0003_seed_wilayas.py"


def gazetteer() -> Gazetteer:
    import importlib.util

    spec = importlib.util.spec_from_file_location("seed", SEED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Gazetteer(module.WILAYAS)


async def corpus(live: bool):
    entries = read_catalog(DEFAULT_CATALOG)
    results = {e.slug: [] for e in entries}
    for entry in entries:
        for path in sorted((DEFAULT_FIXTURES / entry.slug).glob("listing_*")):
            results[entry.slug].append(extract_listing(entry, entry.listings[0], path.read_bytes()))
    if live:
        async with Fetcher(Settings()) as fetcher:
            for entry in entries:
                for url in entry.listings:
                    try:
                        response = await fetcher.get(url, egress=entry.egress)
                    except FetchError as exc:
                        print(f"  {entry.slug}: {exc}", file=sys.stderr)
                        continue
                    if response.ok:
                        results[entry.slug].append(extract_listing(entry, url, response.content))
    articles = []
    for slug, listing_results in results.items():
        for item in merge_listings(listing_results):
            if item.published_at:
                articles.append((slug, item))
    return articles


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--out", type=Path, default=Path("calibration"))
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")

    articles = await corpus(args.live)
    print(f"corpus: {len(articles)} dated articles from {len({s for s, _ in articles})} sources")
    embedder = OpenRouterEmbedder(settings)
    vectors = []
    texts = [embedding_text(item.title, item.lead) for _, item in articles]
    for start in range(0, len(texts), settings.embedding_batch_size):
        vectors += await embedder.embed(texts[start : start + settings.embedding_batch_size])
    await embedder.aclose()
    matrix = np.array(vectors, dtype=np.float32)
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    cosines = matrix @ matrix.T

    places = gazetteer()
    signals = [extract(item.title, item.lead, places) for _, item in articles]
    groups = {"noise": [], "lookalikes": [], "near": []}
    near_pairs, far_pairs = [], []

    def pair(cos, hours, i, j):
        def side(k):
            slug, item = articles[k]
            return {
                "source": slug,
                "id": item.external_id,
                "title": item.title,
                "lead": (item.lead or "")[:160],
                "published_at": item.published_at.isoformat(),
            }

        return {
            "cosine": round(cos, 4),
            "hours_apart": round(hours, 1),
            "conflicts": conflicts(signals[i], signals[j]),
            "a": side(i),
            "b": side(j),
        }

    for i, j in combinations(range(len(articles)), 2):
        (slug_a, a), (slug_b, b) = articles[i], articles[j]
        if slug_a == slug_b:
            continue
        hours = abs((a.published_at - b.published_at).total_seconds()) / 3600
        cos = float(cosines[i, j])
        shared = set(signals[i].entities) & set(signals[j].entities) or (
            set(signals[i].wilayas) & set(signals[j].wilayas)
        )
        if hours <= 36:
            groups["near"].append(cos)
            if cos >= 0.6:
                near_pairs.append(pair(cos, hours, i, j))
        elif hours > 48:
            groups["lookalikes" if shared else "noise"].append(cos)
            if cos >= 0.8:
                far_pairs.append(pair(cos, hours, i, j))

    print(f"{'group':11} {'pairs':>7} {'p50':>6} {'p90':>6} {'p99':>6} {'max':>6}")
    for name, values in groups.items():
        if values:
            v = np.array(values)
            print(
                f"{name:11} {len(v):7d} {np.percentile(v, 50):6.3f} {np.percentile(v, 90):6.3f} "
                f"{np.percentile(v, 99):6.3f} {v.max():6.3f}"
            )
    for threshold in (0.80, 0.85, 0.90):
        print(f"near pairs >= {threshold}: {sum(c >= threshold for c in groups['near'])}")
    args.out.mkdir(parents=True, exist_ok=True)
    near_pairs.sort(key=lambda p: -p["cosine"])
    (args.out / "pairs.json").write_text(
        json.dumps(near_pairs, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    far_pairs.sort(key=lambda p: -p["cosine"])
    (args.out / "far_pairs.json").write_text(
        json.dumps(far_pairs, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    lookalike_top = sorted(groups["lookalikes"], reverse=True)[:5]
    print("top lookalike cosines:", [round(c, 3) for c in lookalike_top])
    print(f"wrote {args.out / 'pairs.json'} ({len(near_pairs)} near pairs >= 0.6)")


if __name__ == "__main__":
    asyncio.run(main())
