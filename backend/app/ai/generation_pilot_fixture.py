"""Pinned, project-owned synthetic inputs for the generation pilot."""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal, TypedDict
from uuid import UUID

from pydantic import Field, HttpUrl, model_validator

from app.ai.generation import GenerationCode, GenerationResult, generate_reading
from app.ai.guardrails import SafetyCode
from app.ai.intent import AuthorizedEvidence, project_authorized_evidence, resolve_intent
from app.ai.llm_adapter import ClaimChoice, GenerationProvider
from app.ai.rendering import FallbackCode, passage_approval
from app.ai.schemas import Locale
from app.ai.validator import GroundingCode, GroundingEvidence
from app.api.schemas.chart import ChartFactUnits, ChartSnapshotResponse
from app.calc.facts import ChartFactPlacement, ChartFacts, ChartMetadata, ChartSettings
from app.db.models.profile import InputCalendar, TimeCertainty
from app.knowledge.chunking import Applicability
from app.knowledge.provenance import Key, Record, Rights, sha256
from app.knowledge.retrieval import Match

FIXTURE_SHA256 = "b76b874f899151f2b03812b050ed9e7380e7f14f76ee53f4688d55785565c3db"
_FIXTURE = Path(__file__).resolve().parents[2] / "tests/fixtures/synthetic-generation-v1.json"
_DATE = datetime(2042, 1, 1, tzinfo=UTC)


class PilotRejected(ValueError):
    """Sanitized diagnostic for pilot setup failure."""


class PilotPassage(Record):
    id: Key
    language: Locale
    target: Applicability
    text: str = Field(min_length=1, max_length=400)


class PilotOffer(Record):
    kind: Literal["chart_fact", "general_explanation", "conditional_interpretation"]
    target: Applicability


class PilotCase(Record):
    id: Key
    question: str = Field(min_length=1, max_length=300)
    language: Locale
    birth_time: Literal["none", "exact", "approximate"] = "none"
    mode: Literal["interpretation", "facts"] = "interpretation"
    passages: tuple[Key, ...] = Field(default=(), max_length=12)
    offers: tuple[PilotOffer, ...] = Field(default=(), max_length=12)
    acceptable_selections: tuple[tuple[int, ...], ...] = ()
    conditional: bool = False
    fallback: FallbackCode | None = None

    def choices(self) -> tuple[ClaimChoice, ...]:
        return tuple(
            ClaimChoice(n, item.kind, item.target) for n, item in enumerate(self.offers, 1)
        )


class PilotFixture(Record):
    version: Literal["kundali-generation-eval-v1"]
    provenance: Literal["original synthetic evaluation fixtures"]
    placement: ChartFactPlacement
    passages: tuple[PilotPassage, ...] = Field(min_length=1, max_length=12)
    cases: tuple[PilotCase, ...] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def check_references(self) -> "PilotFixture":
        ids = {p.id for p in self.passages}
        if len(ids) != len(self.passages) or len({c.id for c in self.cases}) != len(self.cases):
            raise ValueError("Duplicate fixture identifier")
        for case in self.cases:
            if (
                not set(case.passages) <= ids
                or bool(case.offers) == (case.fallback is not None)
                or bool(case.offers) != bool(case.acceptable_selections)
                or any(
                    not row
                    or len(set(row)) != len(row)
                    or not all(1 <= n <= len(case.offers) for n in row)
                    for row in case.acceptable_selections
                )
            ):
                raise ValueError("Inconsistent fixture case")
        return self


def load_fixture(approved_digest: str | None = None) -> PilotFixture:
    artifact = _FIXTURE.read_bytes()
    if sha256(artifact) != FIXTURE_SHA256 or (
        approved_digest is not None and approved_digest != FIXTURE_SHA256
    ):
        raise PilotRejected("The pinned synthetic fixture checksum does not match")
    return PilotFixture.model_validate_json(artifact)


async def run_case(
    fixture: PilotFixture,
    case: PilotCase,
    provider: GenerationProvider,
    *,
    timeout_seconds: float = 8.0,
) -> GenerationResult:
    snapshot = None
    if case.birth_time != "none":
        certainty: Literal[TimeCertainty.EXACT, TimeCertainty.APPROXIMATE] = (
            TimeCertainty.EXACT if case.birth_time == "exact" else TimeCertainty.APPROXIMATE
        )
        snapshot = ChartSnapshotResponse(
            profile_id=UUID(int=1),
            profile_updated_at=_DATE,
            input_calendar=InputCalendar.AD,
            snapshot_id=UUID(int=2),
            time_certainty=certainty,
            schema_version=1,
            profile_revision=1,
            is_current_profile_revision=True,
            created_at=_DATE,
            fact_units=ChartFactUnits(),
            chart=ChartFacts(
                chart_id="synthetic-generation-v1",
                engine_version="engineering-fixture",
                settings=ChartSettings(),
                facts=[fixture.placement],
                metadata=ChartMetadata(
                    ephemeris_source="swieph",
                    julian_day=2466885.5,
                    utc_offset_hours=0,
                    datetime_utc_iso=_DATE.isoformat(),
                ),
            ),
        )
    authorized = project_authorized_evidence(snapshot) if snapshot else AuthorizedEvidence()
    intent = resolve_intent(case.question, authorized)
    by_id = {passage.id: passage for passage in fixture.passages}
    matches = tuple(_match(by_id[identifier], case) for identifier in case.passages)
    evidence = GroundingEvidence(intent, case.language, snapshot, matches=matches)
    return await generate_reading(
        case.question,
        evidence,
        provider,
        mode=case.mode,
        timeout_seconds=timeout_seconds,
        approvals=frozenset(passage_approval(match) for match in matches),
    )


def _match(passage: PilotPassage, case: PilotCase) -> Match:
    return Match(
        citation_id=f"synthetic-generation@1/{passage.id}@1",
        content=passage.text,
        language=passage.language,
        tradition="engineering fixture",
        topic=passage.target.topic,
        locator={"page": "synthetic"},
        source_id="synthetic-generation",
        source_version=1,
        bibliography={"title": "Kundali synthetic generation evaluation"},
        rights=Rights(
            status="project_owned",
            basis="Original engineering fixture",
            holder_or_custodian="Kundali",
            evidence=(HttpUrl("https://example.invalid/fixture"),),
            attribution="Kundali",
            jurisdictions=("evaluation only",),
            permitted_uses=frozenset({"reproduce", "redistribute", "adapt"}),
            reviewed_on=date(2026, 11, 28),
            review_reference="synthetic fixture only",
        ),
        tier=3,
        applicability=passage.target,
        conditional=case.conditional,
    )


class CaseReport(TypedDict):
    case_id: str
    accepted: bool
    matches_label: bool
    expected_selection: bool
    selection: tuple[int, ...]
    generation_attempts: int
    corrections: int
    fallback: FallbackCode | None
    policy: SafetyCode
    failure: GenerationCode | None
    grounding_code: GroundingCode | None
    pipeline_ms: float


def describe_case(case: PilotCase, result: GenerationResult, elapsed_ms: float) -> CaseReport:
    accepted = bool(result.claims)
    accurate = (
        accepted
        and result.selected_options in case.acceptable_selections
        and all(claim.conditional == case.conditional for claim in result.claims)
        if case.offers
        else result.fallback == case.fallback and result.attempts == 0
    )
    return {
        "case_id": case.id,
        "accepted": accepted,
        "matches_label": accurate,
        "expected_selection": bool(case.offers),
        "selection": result.selected_options,
        "generation_attempts": result.attempts,
        "corrections": max(0, result.attempts - 1),
        "fallback": result.fallback,
        "policy": result.policy.code,
        "failure": result.failure,
        "grounding_code": result.grounding_code,
        "pipeline_ms": round(elapsed_ms, 3),
    }


def summarize(rows: list[CaseReport], should_select: int) -> dict[str, object]:
    correct = sum(
        row["matches_label"] is True and row["expected_selection"] is True for row in rows
    )
    return {
        "cases_evaluated": len(rows),
        "labelled_selection_cases": should_select,
        "selection_accuracy": correct / should_select if should_select else None,
        "grounding_and_safety_accepted": sum(row["accepted"] is True for row in rows),
        "abstentions": sum(row["fallback"] is not None for row in rows),
        "correction_attempts": sum(row["corrections"] for row in rows),
        "cases": rows,
    }
