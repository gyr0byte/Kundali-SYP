"""Public request and response contracts for locally selected chat."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from app.ai.guardrails import MAX_QUESTION_CHARS
from app.ai.rendering import FallbackCode
from app.ai.schemas import CitationReference, ClaimKind, Locale
from app.db.models.profile import TimeCertainty
from app.knowledge.chunking import Applicability
from app.knowledge.provenance import Label, Language, Record, Version

MAX_CHAT_BODY_BYTES = 4096
MAX_CHAT_RESPONSE_BYTES = 12 * 1024


class ChatRequest(Record):
    question: Annotated[
        str,
        StringConstraints(
            strict=True, strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS
        ),
    ]
    language: Locale = "en"
    snapshot_id: UUID | None = None


class ChatClaim(Record):
    kind: ClaimKind
    target: Applicability
    text: str = Field(min_length=1, max_length=400)
    conditional: bool
    citation_id: CitationReference | None = None


class ChatCitation(Record):
    citation_id: CitationReference
    source_version: Version
    language: Language
    tier: Literal[1, 2, 3]
    title: Label
    author: Label | None = None
    edition: Label | None = None
    chapter: Label | None = None
    page: Label | None = None
    verse: Label | None = None
    attribution: Label


class ChatSnapshotContext(Record):
    snapshot_id: UUID
    is_current_profile_revision: bool
    time_certainty: TimeCertainty


class ChatResponse(Record):
    language: Locale
    outcome: Literal["answered"] | FallbackCode
    answer: str = Field(min_length=1, max_length=2000)
    claims: tuple[ChatClaim, ...] = Field(default=(), max_length=1)
    citations: tuple[ChatCitation, ...] = Field(default=(), max_length=1)
    disclaimer: Annotated[str, Field(max_length=400)] | None = None
    snapshot: ChatSnapshotContext | None = None
    evaluated_at: datetime | None = None
