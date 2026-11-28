"""Typed embedding contract. Query input is restricted to known chart concepts."""

import hashlib
import math
from collections.abc import Sequence
from typing import Annotated, Final, Literal, Protocol

from pydantic import Field

from app.knowledge.chunking import Applicability
from app.knowledge.provenance import Label, Record, canonical_bytes

DIMENSION: Final = 384
Vector = tuple[float, ...]


class EmbeddingError(RuntimeError):
    """Safe diagnostic for embedding failures."""


class EmbeddingUnavailable(EmbeddingError):
    """The selected provider could not produce an embedding."""


class InvalidEmbedding(EmbeddingError):
    """The provider returned an invalid vector."""


class EmbeddingConfig(Record):
    provider: Label
    model: Label
    model_revision: Label | None = None
    location: Label | None = None
    dimension: Literal[384] = DIMENSION
    query_encoding: Label
    document_encoding: Label
    preprocessing: Label
    normalization: Label


class EmbeddingQuery(Record):
    targets: Annotated[tuple[Applicability, ...], Field(min_length=1, max_length=8)]

    def encode(self) -> str:
        records = {
            canonical_bytes(target.model_dump(mode="json", exclude_none=True))
            for target in self.targets
        }
        return "\n".join(record.decode("utf-8") for record in sorted(records))


class EmbeddingProvider(Protocol):
    @property
    def config(self) -> EmbeddingConfig: ...

    def embed_query(self, query: EmbeddingQuery) -> Vector: ...

    def embed_document(self, text: str) -> Vector: ...


def normalize_vector(values: Sequence[float]) -> Vector:
    if len(values) != DIMENSION:
        raise InvalidEmbedding("Embedding has an unexpected dimension")
    try:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            for value in values
        ):
            raise InvalidEmbedding("Embedding contains invalid components")
    except OverflowError:
        raise InvalidEmbedding("Embedding contains invalid components") from None
    scale = max(abs(value) for value in values)
    if scale == 0:
        raise InvalidEmbedding("Embedding has zero norm")
    scaled = tuple(value / scale for value in values)
    norm = math.hypot(*scaled)
    return tuple(value / norm for value in scaled)


class SyntheticEmbeddingProvider:
    """Deterministic test provider without a network or a model."""

    config = EmbeddingConfig(
        provider="synthetic",
        model="sha256-features",
        model_revision="1",
        query_encoding="query-v1",
        document_encoding="document-v1",
        preprocessing="as-provided-v1",
        normalization="l2-v1",
    )

    def embed_query(self, query: EmbeddingQuery) -> Vector:
        return self._embed("query-v1", query.encode())

    def embed_document(self, text: str) -> Vector:
        return self._embed("document-v1", text)

    @staticmethod
    def _embed(role: str, content: str) -> Vector:
        seed = canonical_bytes([role, content])
        values = hashlib.shake_256(seed).digest(DIMENSION)
        return normalize_vector([value - 127.5 for value in values])
