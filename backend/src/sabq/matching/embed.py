"""Embeddings for story matching (decision 2026-10-19): Voyage AI `voyage-4` through OpenRouter's
OpenAI-compatible endpoint. Behind one interface (`Embedder.embed`) so the provider can change;
changing the model means re-embedding open articles and re-checking thresholds.

Only an article's title and lead are sent (both public on the source site, never body text).
Requests are batched; 429/5xx/network errors are retried with backoff, then raised as
`EmbeddingError`, and the caller leaves the articles `pending` for a later try.
"""

import asyncio
import logging
from typing import Protocol

import httpx2

from sabq.db.models import EMBEDDING_DIMENSIONS
from sabq.settings import Settings

log = logging.getLogger(__name__)
RETRIES = 3


class EmbeddingError(Exception):
    def __init__(self, message: str, *, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def embedding_text(title: str, lead: str | None) -> str:
    return f"{title}\n{lead}" if lead else title


class OpenRouterEmbedder:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        sleep=asyncio.sleep,
    ):
        if settings.openrouter_api_key is None:
            raise ValueError("OPENROUTER_API_KEY is not set")
        self.model = settings.embedding_model
        self.sleep = sleep
        self.client = httpx2.AsyncClient(
            base_url=settings.embedding_base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key.get_secret_value()}",
                "HTTP-Referer": settings.public_base_url,
                "X-Title": "Sabq",
            },
            timeout=httpx2.Timeout(settings.embedding_timeout_s),
            transport=transport,
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        delay = 2.0
        for attempt in range(1, RETRIES + 1):
            try:
                response = await self.client.post(
                    "/embeddings", json={"model": self.model, "input": texts}
                )
            except httpx2.TransportError as exc:
                error = EmbeddingError(f"embeddings: {type(exc).__name__}: {exc}")
            else:
                if response.status_code == 200:
                    return self._vectors(response.json(), len(texts))
                retryable = response.status_code == 429 or response.status_code >= 500
                error = EmbeddingError(
                    f"embeddings: HTTP {response.status_code}: {response.text[:200]}",
                    retryable=retryable,
                )
                if not retryable:
                    raise error
            if attempt < RETRIES:
                log.warning("%s (attempt %d, retrying in %.0f s)", error, attempt, delay)
                await self.sleep(delay)
                delay *= 2
        raise error

    def _vectors(self, body: dict, expected: int) -> list[list[float]]:
        try:
            items = sorted(body["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:
            raise EmbeddingError(f"embeddings: unexpected answer ({exc})") from None
        if len(vectors) != expected or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingError(
                f"embeddings: expected {expected} vectors of {EMBEDDING_DIMENSIONS} dimensions"
            )
        return vectors
