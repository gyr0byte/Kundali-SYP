"""Reproducible evaluation in an isolated in-memory corpus."""

import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter_ns
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ai.embeddings import Vector
from app.ai.intent import (
    AuthorizedEvidence,
    IntentResolution,
    Scope,
    Status,
    canonical_keyword_text,
    intent_search,
    resolve_intent,
)
from app.ai.retrieval import semantic_match
from app.db.base import Base
from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.knowledge.chunking import Applicability
from app.knowledge.provenance import Key, Record, sha256
from app.knowledge.retrieval import (
    DashaEvidence,
    Evaluation,
    Match,
    PlacementEvidence,
    Search,
    retrieve,
    search_statement,
)

FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/multilingual-retrieval-v1.json"


class EvidenceFixture(Record):
    placements: tuple[PlacementEvidence, ...] = Field(default=(), max_length=16)
    dashas: tuple[DashaEvidence, ...] = Field(default=(), max_length=3)
    evaluation: Evaluation | None = None
    current_dasha_lookup: bool = False

    def local_evidence(self) -> AuthorizedEvidence:
        return AuthorizedEvidence(
            self.placements, self.dashas, self.evaluation, self.current_dasha_lookup
        )


class Passage(Record):
    id: Key
    language: Literal["en", "ne"]
    rule: Applicability
    text: str = Field(min_length=1, max_length=600)
    tier: Literal[2, 3]
    state: Literal["approved", "pending", "disabled", "withdrawn", "test", "unresolved"]


class Case(Record):
    id: Key
    group: Key
    language: Literal["en", "ne", "roman-ne", "mixed"]
    question: str = Field(min_length=1, max_length=300)
    chart: Key | None = None
    status: Status
    scope: Scope | None = None
    target: Applicability | None = None
    # Grade 0 denotes a permissible but irrelevant document, omission denotes inadmissible.
    judgments: dict[Key, Literal[0, 1, 2]]


class Dataset(Record):
    version: Literal["kundali-retrieval-eval-v1"]
    provenance: Literal["project-owned synthetic engineering fixtures"]
    charts: dict[Key, EvidenceFixture]
    passages: tuple[Passage, ...]
    cases: tuple[Case, ...]

    @model_validator(mode="after")
    def check_references(self) -> "Dataset":
        passages = {p.id: p for p in self.passages}
        if len(passages) != len(self.passages) or len({c.id for c in self.cases}) != len(
            self.cases
        ):
            raise ValueError("Duplicate fixture identifier")
        for case in self.cases:
            if case.chart and case.chart not in self.charts:
                raise ValueError("Unknown synthetic chart")
            if (case.status == "resolved") != (case.scope is not None and case.target is not None):
                raise ValueError("Resolved labels require a scope and target")
            if any(
                key not in passages or passages[key].state != "approved" for key in case.judgments
            ):
                raise ValueError("Judgment refers to a non-serving passage")
        return self


def load_dataset() -> tuple[Dataset, str]:
    artifact = FIXTURE.read_bytes()
    return Dataset.model_validate_json(artifact), sha256(artifact)


@dataclass(frozen=True)
class PreparedCase:
    case: Case
    evidence: AuthorizedEvidence
    resolution: IntentResolution
    intent_ms: float


def prepare(dataset: Dataset) -> tuple[PreparedCase, ...]:
    prepared = []
    for case in dataset.cases:
        evidence = (
            dataset.charts[case.chart].local_evidence() if case.chart else AuthorizedEvidence()
        )
        start = perf_counter_ns()
        result = resolve_intent(case.question, evidence)
        prepared.append(PreparedCase(case, evidence, result, _elapsed_ms(start)))
    return tuple(prepared)


def _elapsed_ms(start: int) -> float:
    return (perf_counter_ns() - start) / 1_000_000


def _seed(session: Session, passages: tuple[Passage, ...]) -> None:
    """Production-shaped gates are exercised inside this isolated SQLite fixture only."""
    for passage in passages:
        digest = sha256(passage.text.encode("utf-8"))
        rights_status = {"withdrawn": "excluded", "unresolved": "unresolved"}.get(
            passage.state, "project_owned"
        )
        approved = passage.state != "pending"
        session.add(
            KnowledgeSource(
                source_id=passage.id,
                version=1,
                tier=passage.tier,
                collection="test" if passage.state == "test" else "production",
                enabled=passage.state in {"approved", "pending"},
                rights_status=rights_status,
                publication_review="evaluation only",
                bibliography={"title": "Synthetic engineering fixture"},
                rights={
                    "status": rights_status,
                    "basis": "Project-owned evaluation fixture",
                    "holder_or_custodian": "Kundali",
                    "evidence": ["https://example.invalid/fixture"],
                    "attribution": "Kundali evaluation fixture",
                    "jurisdictions": ["evaluation only"],
                    "permitted_uses": (
                        ["reproduce", "redistribute", "adapt", "third_party_processing"]
                        if rights_status == "project_owned"
                        else []
                    ),
                    "reviewed_on": "2026-11-28",
                    "review_reference": "fixture, no editorial approval",
                },
                artifact_sha256=digest,
                content_sha256=digest,
                manifest_sha256=digest,
            )
        )
        session.flush()
        session.add(
            KnowledgeChunk(
                citation_id=f"{passage.id}@1/passage@1",
                source_id=passage.id,
                source_version=1,
                chunk_key="passage",
                revision=1,
                language=passage.language,
                topic=passage.rule.topic,
                tradition="synthetic fixture",
                locator={"page": "fixture"},
                content=passage.text,
                content_sha256=digest,
                applicability=passage.rule.model_dump(mode="json", exclude_none=True),
                editorial_status="approved" if approved else "pending",
                editorial_review="fixture only" if approved else None,
            )
        )


@dataclass(frozen=True)
class EvaluationRow:
    prepared: PreparedCase
    ids: tuple[str, ...]
    retrieval_ms: float | None


def _rate(numerator: float, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def measure(rows: tuple[EvaluationRow, ...], published: set[str]) -> dict[str, int | float | None]:
    ranking_count = topic_count = abstention_count = unsupported_count = 0
    intent_hits = topic_hits = entity_hits = abstention_hits = unsupported_hits = 0
    recall1 = recall5 = ndcg = mrr = 0.0
    violations = leaks = 0
    for row in rows:
        case, prediction = row.prepared.case, row.prepared.resolution
        targets = prediction.intent.targets if prediction.intent else ()
        target = targets[0] if len(targets) == 1 else None
        intent_hits += (prediction.status, prediction.scope, target) == (
            case.status,
            case.scope,
            case.target,
        )
        if case.target is not None:
            topic_count += 1
            topic_hits += target is not None and target.topic == case.target.topic
            entity_hits += target == case.target
        if case.status != "resolved":
            abstention_count += 1
            abstention_hits += prediction.intent is None and not row.ids
        if case.status == "unsupported":
            unsupported_count += 1
            unsupported_hits += prediction.intent is None and not row.ids
        violations += sum(item not in case.judgments and item in published for item in row.ids)
        leaks += sum(item not in published for item in row.ids)
        relevant = {item for item, grade in case.judgments.items() if grade > 0}
        if not relevant:
            continue
        ranking_count += 1
        recall1 += len(set(row.ids[:1]) & relevant) / len(relevant)
        recall5 += len(set(row.ids[:5]) & relevant) / len(relevant)
        dcg = sum(
            (2 ** case.judgments.get(item, 0) - 1) / math.log2(rank + 2)
            for rank, item in enumerate(row.ids[:5])
        )
        ideal = sum(
            (2**grade - 1) / math.log2(rank + 2)
            for rank, grade in enumerate(sorted(case.judgments.values(), reverse=True)[:5])
        )
        ndcg += dcg / ideal
        mrr += next((1.0 / rank for rank, item in enumerate(row.ids, 1) if item in relevant), 0.0)
    latency = sorted(row.retrieval_ms for row in rows if row.retrieval_ms is not None)
    return {
        "cases": len(rows),
        "ranking_cases": ranking_count,
        "intent_accuracy": _rate(intent_hits, len(rows)),
        "topic_accuracy": _rate(topic_hits, topic_count),
        "entity_accuracy": _rate(entity_hits, topic_count),
        "abstention_accuracy": _rate(abstention_hits, abstention_count),
        "unsupported_abstention_accuracy": _rate(unsupported_hits, unsupported_count),
        "recall_at_1": _rate(recall1, ranking_count),
        "recall_at_5": _rate(recall5, ranking_count),
        "ndcg_at_5": _rate(ndcg, ranking_count),
        "mrr_at_5": _rate(mrr, ranking_count),
        "applicability_violations": violations,
        "publication_leaks": leaks,
        "retrieval_p50_ms": round(latency[math.ceil(len(latency) * 0.50) - 1], 4)
        if latency
        else None,
        "retrieval_p95_ms": round(latency[math.ceil(len(latency) * 0.95) - 1], 4)
        if latency
        else None,
    }


def semantic_fixture_rank(
    session: Session,
    search: Search,
    query: Vector,
    documents: dict[str, Vector],
    *,
    tier2_bonus: float,
) -> tuple[Match, ...]:
    """Exact cosine on normalized provider vectors, using serving predicates locally."""
    ranked = []
    for chunk, source in session.execute(search_statement(search)):
        vector = documents.get(source.source_id)
        match = semantic_match(chunk, source, search)
        if vector is None or match is None:
            continue
        cosine = math.fsum(a * b for a, b in zip(query, vector, strict=True))
        score = 1 - max(-1.0, min(1.0, cosine)) - (tier2_bonus if match.tier == 2 else 0)
        ranked.append((score, match.tier, match.citation_id, match))
    ranked.sort(key=lambda row: row[:3])
    return tuple(row[3] for row in ranked[: search.limit])


Ranker = Callable[[Session, Search, PreparedCase], tuple[Match, ...]]


def evaluate(
    dataset: Dataset,
    cases: tuple[PreparedCase, ...],
    ranker: Ranker,
    *,
    canonical_keywords: bool = False,
) -> dict[str, object]:
    engine = create_engine("sqlite://")
    published = {p.id for p in dataset.passages if p.state == "approved"}
    rows = []
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                Base.metadata.tables["knowledge_sources"],
                Base.metadata.tables["knowledge_chunks"],
            ],
        )
        with Session(engine) as session:
            _seed(session, dataset.passages)
            for prepared in cases:
                intent = prepared.resolution.intent
                ids: tuple[str, ...] = ()
                elapsed = None
                if intent is not None:
                    query = (
                        canonical_keyword_text(intent)
                        if canonical_keywords
                        else prepared.case.question
                    )
                    search = intent_search(intent, prepared.evidence, query=query)
                    start = perf_counter_ns()
                    ids = tuple(match.source_id for match in ranker(session, search, prepared))
                    elapsed = _elapsed_ms(start)
                rows.append(EvaluationRow(prepared, ids, elapsed))
    finally:
        engine.dispose()
    result = tuple(rows)
    return {
        "overall": measure(result, published),
        "by_language": {
            lang: measure(
                tuple(row for row in result if row.prepared.case.language == lang), published
            )
            for lang in ("en", "ne", "roman-ne", "mixed")
        },
        "cases": [
            {
                "id": row.prepared.case.id,
                "status": row.prepared.resolution.status,
                "scope": row.prepared.resolution.scope,
                "matches": row.ids,
                "intent_ms": round(row.prepared.intent_ms, 4),
                "retrieval_ms": row.retrieval_ms,
            }
            for row in result
        ],
    }


def keyword_comparisons(dataset: Dataset, cases: tuple[PreparedCase, ...]) -> dict[str, object]:
    def keyword(session: Session, search: Search, _: PreparedCase) -> tuple[Match, ...]:
        return retrieve(session, search)

    return {
        "original": evaluate(dataset, cases, keyword),
        "canonical": evaluate(dataset, cases, keyword, canonical_keywords=True),
    }
