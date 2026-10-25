"""M8 (2-3/4): embeddings client, matching decisions and clusters (docs/story-matching.md).
Vectors are built by hand so each cosine is exact; no real API calls."""

import asyncio
import json
import math
from datetime import UTC, datetime, timedelta

import httpx2
import pytest
from sqlalchemy import select
from test_data_model import make_article, make_source

from sabq.db.models import (
    Article,
    ArticleEmbedding,
    DedupCandidate,
    StoryCluster,
    StoryClusterMember,
)
from sabq.matching import pipeline
from sabq.matching.embed import EmbeddingError, OpenRouterEmbedder
from sabq.matching.match import current_config, match_article
from sabq.matching.normalize import match_text
from sabq.matching.signals import Signals
from sabq.settings import Settings

MODEL = "voyageai/voyage-4"
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
DIM = 1024


def vector(*components: float) -> list[float]:
    """First components given, the rest zero; normalised to length 1."""
    v = list(components) + [0.0] * (DIM - len(components))
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def at_cosine(c: float, axis: int = 1) -> list[float]:
    """A vector whose cosine with vector(1) is exactly c."""
    v = [0.0] * DIM
    v[0], v[axis] = c, math.sqrt(1 - c * c)
    return v


def article(
    session,
    source,
    external_id,
    vec,
    *,
    title=None,
    hours=0.0,
    signals=None,
    confidence="source_meta",
):
    a = make_article(session, source, external_id, "00")
    a.title = title or f"خبر {external_id}"
    a.published_at = NOW + timedelta(hours=hours)
    a.published_at_confidence = confidence
    a.first_seen_at = NOW + timedelta(hours=hours)
    a.match_text = match_text(a.title, None)
    a.match_signals = (signals or Signals()).to_json()
    a.embedding_status = "done"
    session.add(ArticleEmbedding(article_id=a.id, model=MODEL, embedding=vec))
    session.flush()
    return a


@pytest.fixture
def sources(session):
    return [make_source(session, f"src-{n}") for n in range(4)]


def match(session, a):
    return match_article(session, a, MODEL, NOW, current_config(session))


def cluster_of(session, a) -> int | None:
    return session.scalar(
        select(StoryClusterMember.cluster_id).where(StoryClusterMember.article_id == a.id)
    )


def candidates(session, kind="article"):
    return session.scalars(select(DedupCandidate).where(DedupCandidate.kind == kind)).all()


pytestmark_db = pytest.mark.db


# --- decisions ---------------------------------------------------------------------------------


@pytestmark_db
def test_high_cosine_from_another_source_creates_a_story(session, sources):
    a = article(session, sources[0], "a", vector(1))
    b = article(session, sources[1], "b", at_cosine(0.95), hours=1)
    result = match(session, b)
    assert result.created and cluster_of(session, a) == cluster_of(session, b) == result.joined
    cluster = session.get(StoryCluster, result.joined)
    assert (cluster.status, cluster.representative_article_id) == ("automatic", a.id)  # earlier


@pytestmark_db
def test_same_source_is_never_matched(session, sources):
    article(session, sources[0], "a", vector(1))
    b = article(session, sources[0], "b", at_cosine(0.99))
    assert match(session, b).joined is None and candidates(session) == []


@pytestmark_db
@pytest.mark.parametrize(
    ("cosine", "joined", "review"),
    [(0.95, True, 0), (0.89, False, 1), (0.86, False, 1), (0.84, False, 0)],
)
def test_thresholds(session, sources, cosine, joined, review):
    article(session, sources[0], "a", vector(1))
    b = article(session, sources[1], "b", at_cosine(cosine))
    result = match(session, b)
    assert (result.joined is not None, len(candidates(session))) == (joined, review)


@pytestmark_db
def test_a_hard_conflict_sends_even_a_high_score_to_review(session, sources):
    article(session, sources[0], "a", vector(1), signals=Signals(numbers=[[15, "قتيل"]]))
    b = article(session, sources[1], "b", at_cosine(0.96), signals=Signals(numbers=[[7, "قتيل"]]))
    result = match(session, b)
    assert result.joined is None
    (candidate,) = candidates(session)
    assert candidate.status == "pending"
    assert candidate.signals["conflicts"] == ["numbers: [7] vs [15] قتيل"]  # b vs a
    assert candidate.signals["cosine"] == pytest.approx(0.96, abs=1e-3)


@pytestmark_db
def test_identical_text_groups_even_below_the_threshold(session, sources):
    title = "رئيس الجمهورية يستقبل سفيرة مملكة هولندا"
    article(session, sources[0], "a", vector(1), title=title)
    b = article(session, sources[1], "b", at_cosine(0.80), title=title + " ")
    assert match(session, b).joined is not None


@pytestmark_db
def test_outside_the_time_window_nothing_happens(session, sources):
    article(session, sources[0], "a", vector(1))
    b = article(session, sources[1], "b", at_cosine(0.99), hours=40)  # > 36 h apart
    assert match(session, b).joined is None and candidates(session) == []
    c = article(session, sources[2], "c", at_cosine(0.99, 2), hours=60, confidence="first_seen")
    assert match(session, c).joined is not None  # 72 h window when a date is only "first seen"


# --- clusters --------------------------------------------------------------------------------


@pytestmark_db
def test_no_chaining_average_of_the_best_two(session, sources):
    a = article(session, sources[0], "a", vector(1))
    b = article(session, sources[1], "b", vector(0.95, math.sqrt(1 - 0.95**2)))
    match(session, b)
    # c is close to b (0.92) but far from a (0.80): average 0.86 < 0.90, so it stays out
    y = (0.92 - 0.95 * 0.80) / math.sqrt(1 - 0.95**2)
    c = article(session, sources[2], "c", vector(0.80, y, math.sqrt(1 - 0.80**2 - y**2)))
    assert match(session, c).joined is None
    assert cluster_of(session, c) is None and cluster_of(session, a) == cluster_of(session, b)


@pytestmark_db
def test_second_qualifying_story_is_a_merge_candidate_never_merged(session, sources):
    a = article(session, sources[0], "a", vector(1))
    b = article(session, sources[1], "b", vector(1, 0.05))
    match(session, b)  # story 1: a, b
    c = article(session, sources[2], "c", vector(1, 0, 0.2))
    d = article(session, sources[3], "d", vector(1, 0, 0.25))
    first_story = cluster_of(session, a)
    # c and d would also qualify for story 1; make them a separate story by hand
    story_2 = StoryCluster(status="automatic", last_member_at=NOW)
    session.add(story_2)
    session.flush()
    for x in (c, d):
        session.add(
            StoryClusterMember(
                cluster_id=story_2.id, article_id=x.id, membership="duplicate", confidence=1.0
            )
        )
    story_2.representative_article_id = c.id
    session.flush()
    e = article(session, sources[2], "e", vector(1, 0.02, 0.1), hours=1)
    result = match(session, e)
    assert result.joined in (first_story, story_2.id) and result.merge_candidates == 1
    assert len(candidates(session, "cluster_merge")) == 1
    assert {cluster_of(session, x) for x in (a, b)} == {first_story}  # nothing merged


@pytestmark_db
def test_closed_story_is_not_joined(session, sources):
    a = article(session, sources[0], "a", vector(1), hours=-80)
    b = article(session, sources[1], "b", at_cosine(0.97), hours=-79)
    match_article(session, b, MODEL, NOW - timedelta(hours=79), current_config(session))
    late = article(session, sources[2], "c", at_cosine(0.97, 2), hours=-50)
    assert match(session, late).joined is None  # story closed 72 h after its last member
    assert cluster_of(session, late) is None and cluster_of(session, a) is not None


# --- pipeline with a fake embedder -------------------------------------------------------------


class FakeEmbedder:
    model = MODEL

    def __init__(self, fail: EmbeddingError | None = None):
        self.fail = fail
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(texts)
        if self.fail:
            raise self.fail
        # same vector for texts about the same thing (by their first word), else orthogonal
        axes = {}
        return [vector(*([0.0] * axes.setdefault(t.split()[0], len(axes)) + [1.0])) for t in texts]


@pytest.fixture
def database(session, connection):
    """Only this test's articles are pending (the dev database may hold real ones)."""
    from sqlalchemy import update
    from sqlalchemy.orm import sessionmaker

    from sabq.ingest.poller import Database

    session.execute(update(Article).values(embedding_status="done"))
    session.flush()
    return Database(
        sessionmaker(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
    )


def pending_article(session, source, external_id, title):
    a = make_article(session, source, external_id, "00")
    a.title, a.published_at, a.first_seen_at = title, NOW, NOW
    session.flush()
    return a


@pytestmark_db
def test_tick_embeds_signals_and_groups(session, sources, database):
    a = pending_article(session, sources[0], "a", "زلزال بقوة 4 درجات في المدية")
    b = pending_article(session, sources[1], "b", "زلزال يضرب ولاية المدية")
    other = pending_article(session, sources[2], "c", "تشيلسي يهزم إيفرتون")
    embedder = FakeEmbedder()
    result = asyncio.run(pipeline.tick(database, embedder, Settings()))
    assert (result.embedded, result.joined, result.clusters_created) == (3, 1, 1)
    assert embedder.calls[0][0] == "زلزال بقوة 4 درجات في المدية"  # title (+ lead), no body
    session.expire_all()
    assert session.get(Article, a.id).embedding_status == "done"
    assert session.get(Article, a.id).match_signals["wilayas"] == ["26"]
    assert cluster_of(session, a) == cluster_of(session, b) and cluster_of(session, other) is None
    assert asyncio.run(pipeline.tick(database, embedder, Settings())).embedded == 0


@pytestmark_db
def test_api_failure_keeps_articles_pending_or_marks_them_failed(session, sources, database):
    a = pending_article(session, sources[0], "a", "خبر")
    result = asyncio.run(pipeline.tick(database, FakeEmbedder(EmbeddingError("503")), Settings()))
    assert result.failed and session.get(Article, a.id).embedding_status == "pending"
    bad = FakeEmbedder(EmbeddingError("HTTP 400", retryable=False))
    asyncio.run(pipeline.tick(database, bad, Settings()))
    session.expire_all()
    assert session.get(Article, a.id).embedding_status == "failed"


# --- the OpenRouter client (no network) ----------------------------------------------------------


def client_with(responses: list[httpx2.Response], seen: list) -> OpenRouterEmbedder:
    def handler(request):
        seen.append(json.loads(request.content))
        return responses.pop(0)

    async def no_sleep(_):
        return None

    settings = Settings(openrouter_api_key="sk-or-test")
    return OpenRouterEmbedder(settings, transport=httpx2.MockTransport(handler), sleep=no_sleep)


def answer(n: int, reverse=False) -> httpx2.Response:
    data = [{"index": i, "embedding": [float(i)] * DIM} for i in range(n)]
    return httpx2.Response(200, json={"data": list(reversed(data)) if reverse else data})


def test_client_orders_by_index_and_retries_429():
    seen = []
    client = client_with([httpx2.Response(429), answer(2, reverse=True)], seen)
    vectors = asyncio.run(client.embed(["a", "b"]))
    assert [v[0] for v in vectors] == [0.0, 1.0]
    assert seen[0] == {"model": MODEL, "input": ["a", "b"]} and len(seen) == 2


def test_client_errors():
    with pytest.raises(EmbeddingError) as bad_request:
        asyncio.run(client_with([httpx2.Response(400, text="bad")], []).embed(["a"]))
    assert not bad_request.value.retryable
    with pytest.raises(EmbeddingError, match="dimensions"):
        short = httpx2.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}]})
        asyncio.run(client_with([short], []).embed(["a"]))
    with pytest.raises(EmbeddingError) as down:
        asyncio.run(client_with([httpx2.Response(503)] * 3, []).embed(["a"]))
    assert down.value.retryable
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterEmbedder(Settings(openrouter_api_key=None))
