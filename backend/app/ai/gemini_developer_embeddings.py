"""Gemini Developer API transport restricted to reviewed evaluation inputs."""

import json
import re
from collections.abc import Callable
from time import monotonic
from typing import Literal

import httpx

from app.ai.embeddings import (
    DIMENSION,
    EmbeddingConfig,
    EmbeddingQuery,
    EmbeddingUnavailable,
    InvalidEmbedding,
    Vector,
    normalize_vector,
)
from app.ai.gemini_embeddings import MAX_ATTEMPTS, AttemptOutcome

_MODEL = "gemini-embedding-001"
_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:embedContent"


class GeminiDeveloperEmbeddings:
    config = EmbeddingConfig(
        provider="google-gemini-developer",
        model=_MODEL,
        query_encoding="RETRIEVAL_QUERY",
        document_encoding="RETRIEVAL_DOCUMENT",
        preprocessing="structured-query-v1-and-verbatim-document-v1",
        normalization="l2-v1",
    )

    def __init__(
        self,
        api_key: Callable[[], str],
        *,
        approved_documents: frozenset[str],
        approved_queries: frozenset[str],
        on_attempt: Callable[[int], None],
        on_attempt_result: Callable[[AttemptOutcome, float], None],
        on_usage: Callable[[int | None], None],
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._documents = approved_documents
        self._queries = approved_queries
        self._on_attempt = on_attempt
        self._on_attempt_result = on_attempt_result
        self._on_usage = on_usage
        self._transport = transport

    def embed_query(self, query: EmbeddingQuery) -> Vector:
        content = query.encode()
        if content not in self._queries:
            raise InvalidEmbedding("Query is outside the reviewed evaluation inputs")
        return self._predict(content, "RETRIEVAL_QUERY")

    def embed_document(self, text: str) -> Vector:
        if text not in self._documents:
            raise InvalidEmbedding("Document is outside the reviewed evaluation inputs")
        return self._predict(text, "RETRIEVAL_DOCUMENT")

    def _predict(
        self,
        content: str,
        task: Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"],
    ) -> Vector:
        try:
            key = self._api_key()
            if not re.fullmatch(r"(?:AIza[A-Za-z0-9_-]{35}|AQ\.[A-Za-z0-9_-]{17,253})", key):
                raise ValueError
        except Exception:
            raise EmbeddingUnavailable(
                "Gemini Developer API authentication is unavailable"
            ) from None
        with httpx.Client(
            timeout=httpx.Timeout(4, connect=2),
            trust_env=False,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            deadline = monotonic() + 8
            for _ in range(MAX_ATTEMPTS):
                if monotonic() >= deadline:
                    break
                self._on_attempt(len(content.encode("utf-8")))
                started = monotonic()
                outcome: AttemptOutcome = "invalid_response"
                try:
                    with client.stream(
                        "POST",
                        _ENDPOINT,
                        headers={"x-goog-api-key": key, "Accept-Encoding": "identity"},
                        json={
                            "model": f"models/{_MODEL}",
                            "content": {"parts": [{"text": content}]},
                            "taskType": task,
                            "outputDimensionality": DIMENSION,
                        },
                    ) as response:
                        if response.status_code == 429:
                            outcome = "quota_exhausted"
                            raise EmbeddingUnavailable("Gemini Developer API quota exhausted")
                        if response.status_code in {500, 502, 503, 504}:
                            outcome = "transient_http"
                            continue
                        if response.status_code != 200:
                            outcome = "rejected_http"
                            raise EmbeddingUnavailable("Gemini Developer API refused the request")
                        data = bytearray()
                        for part in response.iter_bytes():
                            if monotonic() >= deadline:
                                outcome = "deadline"
                                raise EmbeddingUnavailable("Gemini Developer API deadline exceeded")
                            if len(data) + len(part) > 65536:
                                raise InvalidEmbedding("Gemini Developer API response is too large")
                            data.extend(part)
                        vector, tokens = _decode(data)
                        self._on_usage(tokens)
                        outcome = "ok"
                        return vector
                except (httpx.TransportError, httpx.DecodingError):
                    outcome = "transport_failure"
                finally:
                    self._on_attempt_result(outcome, (monotonic() - started) * 1000)
        raise EmbeddingUnavailable("Gemini Developer API request did not complete") from None


def _decode(data: bytearray) -> tuple[Vector, int | None]:
    try:
        payload = json.loads(data)
        values = payload["embedding"]["values"]
        if not isinstance(values, list):
            raise ValueError
    except (KeyError, TypeError, ValueError, RecursionError):
        raise InvalidEmbedding("Gemini Developer API returned an invalid payload") from None
    usage = payload.get("usageMetadata")
    tokens = usage.get("promptTokenCount") if isinstance(usage, dict) else None
    return normalize_vector(values), tokens if type(tokens) is int and tokens >= 0 else None
