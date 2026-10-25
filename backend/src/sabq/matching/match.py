"""Candidates, decisions and clusters (docs/story-matching.md, pipeline steps 3-5).

For an embedded article A:
  1. candidates: articles from *other* sources within ±36 h (±72 h when either date is only
     "first seen"), the 20 nearest by embedding (pgvector, cosine);
  2. each pair: cosine, hard conflicts (numbers, dates, wilayas, countries named in the text),
     shared signals, lexical overlap, hours apart; all kept as evidence;
  3. decision: identical normalised text -> automatic; cosine >= automatic threshold and no
     conflict -> automatic; cosine >= review threshold -> a pending review candidate; else nothing;
  4. A joins the open cluster whose score (average of A's best two member cosines, no conflict
     with them) clears the automatic threshold; a second qualifying cluster is recorded as a
     merge candidate, never merged. No cluster but an automatic match without one: a new cluster.

Precision over recall: anything uncertain stays apart and is recorded for review.
Thresholds and windows come from the latest `story_matching_config` row (seeded with the
defaults below); `scorer_version` on every candidate says which one decided.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from sabq.db.models import (
    Article,
    ArticleEmbedding,
    DedupCandidate,
    Source,
    StoryCluster,
    StoryClusterMember,
    StoryMatchingConfig,
)
from sabq.matching.normalize import tokens
from sabq.matching.signals import Signals, conflicts

log = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "thresholds": {"automatic": 0.90, "review": 0.85},
    "windows": {
        "candidate_hours": 36,
        "low_confidence_hours": 72,
        "cluster_hours": 72,
        "neighbours": 20,
    },
    "weights": {},  # v1 decides on cosine + conflicts; weights come with a labelled set
}
TIER_RANK = {"priority": 0, "normal": 1, "secondary": 2}


@dataclass
class MatchingConfig:
    version: int
    automatic: float
    review: float
    candidate_hours: float
    low_confidence_hours: float
    cluster_hours: float
    neighbours: int


def current_config(session: Session) -> MatchingConfig:
    row = session.scalar(select(StoryMatchingConfig).order_by(StoryMatchingConfig.version.desc()))
    if row is None:
        row = StoryMatchingConfig(version=1, created_by="default", **DEFAULT_CONFIG)
        session.add(row)
        session.flush()
    t, w = row.thresholds, row.windows
    return MatchingConfig(
        version=row.version,
        automatic=t["automatic"],
        review=t["review"],
        candidate_hours=w["candidate_hours"],
        low_confidence_hours=w["low_confidence_hours"],
        cluster_hours=w["cluster_hours"],
        neighbours=w["neighbours"],
    )


@dataclass
class Pair:
    other: Article
    cosine: float
    exact: bool = False
    conflicts: list[str] = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    decision: str | None = None  # automatic | review | None

    @property
    def score(self) -> float:
        return 1.0 if self.exact else self.cosine


@dataclass
class MatchResult:
    joined: int | None = None  # cluster id
    created: bool = False
    review: int = 0
    merge_candidates: int = 0


def when(article: Article) -> datetime:
    return article.published_at or article.first_seen_at


def candidates(session: Session, article: Article, model: str, cfg: MatchingConfig) -> list[Pair]:
    vector = session.scalar(
        select(ArticleEmbedding.embedding).where(
            ArticleEmbedding.article_id == article.id, ArticleEmbedding.model == model
        )
    )
    if vector is None:
        return []
    hours = cfg.candidate_hours
    if article.published_at_confidence == "first_seen":
        hours = cfg.low_confidence_hours
    at, span = when(article), timedelta(hours=cfg.low_confidence_hours)
    distance = ArticleEmbedding.embedding.cosine_distance(vector)
    rows = session.execute(
        select(Article, (1 - distance).label("cosine"))
        .join(
            ArticleEmbedding,
            (ArticleEmbedding.article_id == Article.id) & (ArticleEmbedding.model == model),
        )
        .where(
            Article.source_id != article.source_id,
            func.coalesce(Article.published_at, Article.first_seen_at).between(
                at - span, at + span
            ),
        )
        .order_by(distance)
        .limit(cfg.neighbours)
    ).all()
    pairs = []
    for other, cosine in rows:
        limit = hours if other.published_at_confidence != "first_seen" else cfg.low_confidence_hours
        if abs((when(other) - at).total_seconds()) <= limit * 3600:
            pairs.append(Pair(other, float(cosine)))
    return pairs


def judge(article: Article, pair: Pair, cfg: MatchingConfig) -> Pair:
    mine, theirs = (
        Signals.from_json(article.match_signals),
        Signals.from_json(pair.other.match_signals),
    )
    pair.exact = bool(article.match_text) and article.match_text == pair.other.match_text
    pair.conflicts = conflicts(mine, theirs)
    words_a = set(tokens(article.match_text or ""))
    words_b = set(tokens(pair.other.match_text or ""))
    pair.evidence = {
        "cosine": round(pair.cosine, 4),
        "exact": pair.exact,
        "conflicts": pair.conflicts,
        "lexical": round(len(words_a & words_b) / len(words_a | words_b), 3)
        if words_a and words_b and article.language == pair.other.language
        else None,
        "shared": {
            "numbers": [n for n in mine.numbers if n in theirs.numbers],
            "wilayas": sorted(set(mine.wilayas) & set(theirs.wilayas)),
            "countries": sorted(set(mine.countries) & set(theirs.countries)),
            "entities": sorted(set(mine.entities) & set(theirs.entities)),
        },
        "hours_apart": round(abs((when(article) - when(pair.other)).total_seconds()) / 3600, 1),
        "scorer_version": cfg.version,
    }
    pair.decision = decision(pair.cosine, pair.exact, pair.conflicts, cfg)
    return pair


def decision(cosine: float, exact: bool, found_conflicts: list[str], cfg) -> str | None:
    """automatic | review | None, for a pair already within the time window."""
    if exact or (cosine >= cfg.automatic and not found_conflicts):
        return "automatic"
    if cosine >= cfg.review:
        return "review"
    return None


def match_article(
    session: Session, article: Article, model: str, now: datetime, cfg: MatchingConfig
) -> MatchResult:
    result = MatchResult()
    if _cluster_of(session, article.id) is not None:
        return result  # already grouped; leaving a cluster is a recorded split, never automatic
    pairs = [judge(article, pair, cfg) for pair in candidates(session, article, model, cfg)]

    for pair in pairs:
        if pair.decision == "review" and _new_candidate(session, article.id, pair.other.id):
            session.add(
                DedupCandidate(
                    kind="article",
                    article_id=article.id,
                    candidate_article_id=pair.other.id,
                    score=pair.score,
                    signals=pair.evidence,
                    scorer_version=cfg.version,
                )
            )
            result.review += 1

    automatic = [p for p in pairs if p.decision == "automatic"]
    if not automatic:
        return result
    by_cluster: dict[int | None, list[Pair]] = {}
    for pair in automatic:
        by_cluster.setdefault(_open_cluster_of(session, pair.other.id, now, cfg), []).append(pair)

    qualifying = []
    for cluster_id in [c for c in by_cluster if c is not None and c > 0]:  # open clusters
        score, evidence = _cluster_score(session, article, cluster_id, model, cfg)
        if score is not None and score >= cfg.automatic:
            qualifying.append((score, cluster_id, evidence))
    qualifying.sort(reverse=True)

    if qualifying:
        score, cluster_id, evidence = qualifying[0]
        _join(session, cluster_id, article, score, evidence, now)
        result.joined = cluster_id
        for _, other_cluster, other_evidence in qualifying[1:]:
            representative = session.get(StoryCluster, other_cluster).representative_article_id
            if representative and _new_candidate(
                session, article.id, representative, "cluster_merge"
            ):
                session.add(
                    DedupCandidate(
                        kind="cluster_merge",
                        article_id=article.id,
                        candidate_article_id=representative,
                        score=other_evidence["cluster_score"],
                        signals=other_evidence,
                        scorer_version=cfg.version,
                    )
                )
                result.merge_candidates += 1
        return result

    loose = [p for p in by_cluster.get(None, []) if _cluster_of(session, p.other.id) is None]
    if loose:
        best = max(loose, key=lambda p: p.score)
        cluster = StoryCluster(status="automatic", last_member_at=now)
        session.add(cluster)
        session.flush()
        session.add(
            StoryClusterMember(
                cluster_id=cluster.id,
                article_id=best.other.id,
                membership="duplicate",
                confidence=1.0,
                evidence={"founder": True},
            )
        )
        _join(session, cluster.id, article, best.score, best.evidence, now)
        result.joined, result.created = cluster.id, True
    return result


# --- clusters --------------------------------------------------------------------------------


def _cluster_of(session: Session, article_id: int) -> int | None:
    return session.scalar(
        select(StoryClusterMember.cluster_id).where(StoryClusterMember.article_id == article_id)
    )


def _open_cluster_of(
    session: Session, article_id: int, now: datetime, cfg: MatchingConfig
) -> int | None:
    """The article's cluster if still open (a cluster closes `cluster_hours` after its last
    member joined); None if it has no cluster. A closed cluster counts as no cluster for joining
    but its members never found a new one (they are already grouped)."""
    cluster_id = _cluster_of(session, article_id)
    if cluster_id is None:
        return None
    cluster = session.get(StoryCluster, cluster_id)
    is_open = cluster.closed_at is None and cluster.last_member_at >= now - timedelta(
        hours=cfg.cluster_hours
    )
    if not is_open and cluster.closed_at is None:
        cluster.closed_at = cluster.last_member_at + timedelta(hours=cfg.cluster_hours)
    return cluster_id if is_open else -cluster_id  # negative: closed, never joined


def _cluster_score(session, article, cluster_id, model, cfg) -> tuple[float | None, dict]:
    """Average of the article's best two cosines to the cluster's members; None on a conflict."""
    vector = session.scalar(
        select(ArticleEmbedding.embedding).where(
            ArticleEmbedding.article_id == article.id, ArticleEmbedding.model == model
        )
    )
    distance = ArticleEmbedding.embedding.cosine_distance(vector)
    rows = session.execute(
        select(Article, (1 - distance).label("cosine"))
        .join(StoryClusterMember, StoryClusterMember.article_id == Article.id)
        .join(
            ArticleEmbedding,
            (ArticleEmbedding.article_id == Article.id) & (ArticleEmbedding.model == model),
        )
        .where(StoryClusterMember.cluster_id == cluster_id)
        .order_by(distance)
        .limit(2)
    ).all()
    if not rows:
        return None, {}
    best = [judge(article, Pair(other, float(cosine)), cfg) for other, cosine in rows]
    if any(pair.conflicts and not pair.exact for pair in best):
        return None, {}
    score = sum(pair.score for pair in best) / len(best)
    evidence = {"cluster_score": round(score, 4), "members": [p.evidence for p in best]}
    return score, evidence


def _join(session, cluster_id, article, score, evidence, now) -> None:
    session.add(
        StoryClusterMember(
            cluster_id=cluster_id,
            article_id=article.id,
            membership="duplicate",
            confidence=round(score, 4),
            evidence=evidence,
        )
    )
    session.flush()
    cluster = session.get(StoryCluster, cluster_id)
    cluster.last_member_at = now
    members = session.execute(
        select(Article, Source.tier)
        .join(StoryClusterMember, StoryClusterMember.article_id == Article.id)
        .join(Source, Source.id == Article.source_id)
        .where(StoryClusterMember.cluster_id == cluster_id)
    ).all()
    # representative: earliest reliable publication, then source tier, then first seen
    representative = min(
        members,
        key=lambda m: (
            m[0].published_at_confidence == "first_seen",
            when(m[0]),
            TIER_RANK.get(m[1], 9),
            m[0].first_seen_at,
        ),
    )[0]
    cluster.representative_article_id = representative.id
    dated = [m[0].published_at for m in members if m[0].published_at]
    cluster.first_published_at = min(dated) if dated else None


def _new_candidate(session, article_id: int, other_id: int, kind: str = "article") -> bool:
    exists = session.scalar(
        select(DedupCandidate.id).where(
            DedupCandidate.kind == kind,
            or_(
                (DedupCandidate.article_id == article_id)
                & (DedupCandidate.candidate_article_id == other_id),
                (DedupCandidate.article_id == other_id)
                & (DedupCandidate.candidate_article_id == article_id),
            ),
        )
    )
    return exists is None
