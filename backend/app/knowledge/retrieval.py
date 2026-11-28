"""Local metadata-first keyword retrieval over reviewed knowledge releases."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from unicodedata import category, normalize
from uuid import UUID

from pydantic import Field, TypeAdapter, ValidationError
from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session

from app.calc.dasha import DashaLevel, DashaLord
from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.chunking import (
    Applicability,
    DashaRule,
    House,
    NakshatraRule,
    Pada,
    PadaRule,
    Planet,
    PlanetInHouse,
    PlanetInSign,
    Sign,
    Topic,
)
from app.knowledge.provenance import CLEARED, Label, Language, Record, Rights


class PlacementEvidence(Record):
    planet: Planet
    house: House | None = None
    sign: Sign | None = None
    nakshatra: Label | None = None
    pada: Pada | None = None
    certainty: Literal["exact", "approximate", "uncertain"]


class Evaluation(Record):
    snapshot_id: UUID
    instant: datetime


class DashaEvidence(Record):
    evaluation: Evaluation
    method: Literal["vimshottari-v1"]
    level: DashaLevel
    lord: DashaLord
    parent_lord: DashaLord | None = None
    certainty: Literal["exact", "approximate"]


class Search(Record):
    query: Annotated[str, Field(max_length=300)]
    topics: tuple[Topic, ...] = Field(min_length=1, max_length=8)
    languages: tuple[Language, ...] = Field(min_length=1, max_length=8)
    limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 8
    placements: tuple[PlacementEvidence, ...] = Field(default=(), max_length=16)
    dashas: tuple[DashaEvidence, ...] = Field(default=(), max_length=3)
    evaluation: Evaluation | None = None


class Citation(Record):
    citation_id: str
    content: str
    language: Language
    tradition: str
    topic: Topic
    locator: dict[str, object]
    source_id: str
    source_version: int
    bibliography: dict[str, object]
    rights: Rights
    tier: int


class Match(Citation):
    conditional: bool


_RULE = TypeAdapter(Applicability)


def _tokens(text: str) -> set[str]:
    folded = normalize("NFKC", text).casefold()
    return set("".join(c if category(c)[0] in "LMN" else " " for c in folded).split())


def _applicable(rule: Applicability, search: Search) -> bool | None:
    """Return conditionality on a match, or None when evidence is absent."""
    if isinstance(rule, DashaRule):
        if search.evaluation is None or search.evaluation.instant.utcoffset() is None:
            return None
        for dasha in search.dashas:
            if (
                dasha.evaluation == search.evaluation
                and (dasha.method, dasha.level, dasha.lord) == (rule.method, rule.level, rule.lord)
                and (rule.parent_lord is None or rule.parent_lord == dasha.parent_lord)
            ):
                return dasha.certainty == "approximate"
        return None
    if not isinstance(rule, PlanetInHouse | PlanetInSign | NakshatraRule | PadaRule):
        return False
    for fact in search.placements:
        if fact.certainty == "uncertain":
            continue
        if isinstance(rule, PlanetInHouse):
            matches = (fact.planet, fact.house) == (rule.planet, rule.house)
        elif isinstance(rule, PlanetInSign):
            matches = (fact.planet, fact.sign) == (rule.planet, rule.sign)
        else:
            matches = (fact.planet, fact.nakshatra) == (rule.body, rule.nakshatra)
            if isinstance(rule, PadaRule):
                matches &= fact.pada == rule.pada
        if matches:
            return fact.certainty == "approximate"
    return None


def eligible_statement(*, current: bool) -> Select[KnowledgeChunk, KnowledgeSource]:
    predicates = [
        KnowledgeSource.collection == "production",
        KnowledgeSource.rights_status.in_(CLEARED),
        KnowledgeSource.publication_review.is_not(None),
        KnowledgeChunk.editorial_status == "approved",
        KnowledgeChunk.editorial_review.is_not(None),
    ]
    if current:
        predicates.append(KnowledgeSource.enabled.is_(True))
    return (
        select(KnowledgeChunk, KnowledgeSource)
        .join(
            KnowledgeSource,
            and_(
                KnowledgeChunk.source_id == KnowledgeSource.source_id,
                KnowledgeChunk.source_version == KnowledgeSource.version,
            ),
        )
        .where(*predicates)
    )


def _citation(
    chunk: KnowledgeChunk, source: KnowledgeSource, rule: Applicability
) -> Citation | None:
    try:
        rights = Rights.model_validate(source.rights)
        if (
            rights.status != source.rights_status
            or rule.topic != chunk.topic
            or not source.publication_review
            or not source.publication_review.strip()
            or not chunk.editorial_review
            or not chunk.editorial_review.strip()
        ):
            return None
        return Citation(
            citation_id=chunk.citation_id,
            content=chunk.content,
            language=chunk.language,
            tradition=chunk.tradition,
            topic=rule.topic,
            locator=chunk.locator,
            source_id=source.source_id,
            source_version=source.version,
            tier=source.tier,
            bibliography=source.bibliography,
            rights=rights,
        )
    except ValidationError:
        return None


def retrieve(session: Session, search: Search) -> tuple[Match, ...]:
    terms = _tokens(search.query)
    if not terms:
        return ()
    matches: list[tuple[int, int, str, Match]] = []
    for chunk, source in session.execute(search_statement(search)):
        match = match_candidate(chunk, source, search)
        if match is None:
            continue
        identifiers = " ".join(
            str(value) for key, value in chunk.applicability.items() if key != "topic"
        )
        score = len(terms & _tokens(chunk.content + " " + identifiers))
        if score:
            matches.append((-score, source.tier, chunk.citation_id, match))
    matches.sort(key=lambda item: item[:3])
    return tuple(item[3] for item in matches[: search.limit])


def search_statement(search: Search) -> Select[KnowledgeChunk, KnowledgeSource]:
    return eligible_statement(current=True).where(
        KnowledgeChunk.topic.in_(search.topics),
        KnowledgeChunk.language.in_(search.languages),
    )


def match_candidate(chunk: KnowledgeChunk, source: KnowledgeSource, search: Search) -> Match | None:
    try:
        rule = _RULE.validate_python(chunk.applicability)
    except ValidationError:
        return None
    conditional = _applicable(rule, search)
    if conditional is None:
        return None
    citation = _citation(chunk, source, rule)
    if citation is None:
        return None
    return Match(**citation.model_dump(), conditional=conditional)


def validated_citation(chunk: KnowledgeChunk, source: KnowledgeSource) -> Citation | None:
    try:
        rule = _RULE.validate_python(chunk.applicability)
    except ValidationError:
        return None
    return _citation(chunk, source, rule)


def resolve_citation(session: Session, citation_id: str) -> Citation | None:
    """Resolve an approved historical citation while the release rights still permit it."""
    row = session.execute(
        eligible_statement(current=False).where(KnowledgeChunk.citation_id == citation_id)
    ).one_or_none()
    if row is None:
        return None
    chunk, source = row
    return validated_citation(chunk, source)
