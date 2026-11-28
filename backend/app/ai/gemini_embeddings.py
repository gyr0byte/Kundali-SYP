"""Regional Vertex AI predict adapter for the Gemini embedding pilot."""

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

_MODEL = "gemini-embedding-001"
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_RESPONSE = 65536
_MAX_ATTEMPTS = 2


class VertexGeminiEmbeddings:
    """Token acquisition is supplied by the operator's trusted server-side adapter."""

    def __init__(
        self,
        project: str,
        location: str,
        access_token: Callable[[], str],
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project):
            raise ValueError("Invalid Vertex project identifier")
        if not re.fullmatch(r"[a-z]+-[a-z]+[0-9]+", location):
            raise ValueError("A regional Vertex location is required")
        self._endpoint = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/{_MODEL}:predict"
        )
        self._get_token = access_token
        self._transport = transport
        self._config = EmbeddingConfig(
            provider="google-vertex",
            model=_MODEL,
            location=location,
            query_encoding="RETRIEVAL_QUERY",
            document_encoding="RETRIEVAL_DOCUMENT",
            preprocessing="structured-query-v1-and-verbatim-document-v1",
            normalization="l2-v1",
        )

    @property
    def config(self) -> EmbeddingConfig:
        return self._config

    def embed_query(self, query: EmbeddingQuery) -> Vector:
        return self._predict(query.encode(), "RETRIEVAL_QUERY")

    def embed_document(self, text: str) -> Vector:
        return self._predict(text, "RETRIEVAL_DOCUMENT")

    def _predict(
        self,
        content: str,
        task: Literal["RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"],
    ) -> Vector:
        if not content.strip() or len(content) > 6000:
            raise InvalidEmbedding("Embedding input is empty or too large")
        try:
            token = self._get_token()
            if not re.fullmatch(r"[A-Za-z0-9._~+/=-]{1,8192}", token):
                raise ValueError
        except Exception:
            raise EmbeddingUnavailable("Vertex authentication is unavailable") from None
        with httpx.Client(
            timeout=httpx.Timeout(4, connect=2),
            trust_env=False,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            deadline = monotonic() + 8
            for _ in range(_MAX_ATTEMPTS):
                if monotonic() >= deadline:
                    break
                try:
                    with client.stream(
                        "POST",
                        self._endpoint,
                        headers={"Authorization": f"Bearer {token}", "Accept-Encoding": "identity"},
                        json={
                            "instances": [{"content": content, "task_type": task}],
                            "parameters": {
                                "outputDimensionality": DIMENSION,
                                "autoTruncate": False,
                            },
                        },
                    ) as response:
                        if response.status_code in _TRANSIENT_STATUS:
                            continue
                        if response.status_code != 200:
                            raise EmbeddingUnavailable("Vertex refused the embedding request")
                        data = bytearray()
                        for part in response.iter_bytes():
                            if monotonic() >= deadline:
                                raise EmbeddingUnavailable("Vertex embedding deadline exceeded")
                            data.extend(part)
                            if len(data) > _MAX_RESPONSE:
                                raise InvalidEmbedding("Vertex response exceeds the size limit")
                        return _decode(data)
                except (httpx.TransportError, httpx.DecodingError):
                    continue
        raise EmbeddingUnavailable("Vertex embedding request did not complete") from None


def _decode(data: bytearray) -> Vector:
    import json

    try:
        (prediction,) = json.loads(data)["predictions"]
        embedding = prediction["embeddings"]
        values = embedding["values"]
        if embedding.get("statistics", {}).get("truncated", False) or not isinstance(values, list):
            raise ValueError
    except (KeyError, TypeError, AttributeError, ValueError, RecursionError):
        raise InvalidEmbedding("Vertex returned an invalid embedding payload") from None
    return normalize_vector(values)
