"""Validate untrusted selections against one server-authorized request."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import ValidationError

from app.ai.intent import IntentResolution, project_authorized_evidence, project_placement
from app.ai.schemas import (
    Abstention,
    ActiveDashaClaim,
    FactClaim,
    GeneralExplanation,
    Interpretation,
    Locale,
    Reading,
)
from app.api.schemas.chart import ChartSnapshotResponse, SnapshotResponse
from app.api.schemas.dasha import DashaActivePeriodFact, DashaResponse
from app.calc.facts import ChartFactPlacement
from app.db.models.profile import TimeCertainty
from app.knowledge.provenance import CLEARED, Record
from app.knowledge.retrieval import (
    Evaluation,
    Match,
    Search,
    applicability_condition,
    matches_target,
)

MAX_RESPONSE_BYTES = 24 * 1024


class GroundingCode(StrEnum):
    RESPONSE_TOO_LARGE = "response_too_large"
    MALFORMED_RESPONSE = "malformed_response"
    LANGUAGE_MISMATCH = "language_mismatch"
    SCOPE_MISMATCH = "scope_mismatch"
    SNAPSHOT_MISMATCH = "snapshot_mismatch"
    BIRTH_TIME_UNSUPPORTED = "birth_time_unsupported"
    FACT_NOT_AUTHORIZED = "fact_not_authorized"
    FACT_MISMATCH = "fact_mismatch"
    DASHA_EVALUATION_MISMATCH = "dasha_evaluation_mismatch"
    TARGET_MISMATCH = "target_mismatch"
    CERTAINTY_MISMATCH = "certainty_mismatch"
    CITATION_NOT_AUTHORIZED = "citation_not_authorized"
    CITATION_INAPPLICABLE = "citation_inapplicable"
    INVALID_EVIDENCE = "invalid_evidence"


@dataclass(frozen=True, slots=True, repr=False)
class GroundingEvidence:
    """Server-only input. The caller authorizes ownership and retrieves live matches."""

    intent: IntentResolution
    language: Locale
    snapshot: SnapshotResponse | None = None
    dasha: DashaResponse | None = None
    evaluation: Evaluation | None = None
    matches: tuple[Match, ...] = ()


class GroundingResult(Record):
    reading: Reading | None = None
    code: GroundingCode | None = None
    claim_index: int | None = None


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Duplicate JSON fields")
    return fields


def _invalid_constant(_: str) -> None:
    raise ValueError("Non-JSON constant")


def _utc(value: datetime) -> datetime | None:
    return value.astimezone(UTC) if value.utcoffset() is not None else None


def _dasha_search(
    claim: ActiveDashaClaim, snapshot: ChartSnapshotResponse, evidence: GroundingEvidence
) -> Search | GroundingCode:
    dasha, expected = evidence.dasha, evidence.evaluation
    if dasha is None:
        return GroundingCode.FACT_NOT_AUTHORIZED
    if dasha.snapshot_id != snapshot.snapshot_id or dasha.chart_id != snapshot.chart.chart_id:
        return GroundingCode.SNAPSHOT_MISMATCH
    if expected is None or expected.snapshot_id != snapshot.snapshot_id:
        return GroundingCode.DASHA_EVALUATION_MISMATCH

    context = project_authorized_evidence(snapshot, dasha)
    if context.evaluation is None or dasha.lookup.periods is None:
        return GroundingCode.INVALID_EVIDENCE
    instant = _utc(expected.instant)
    if (
        instant is None
        or instant != _utc(context.evaluation.instant)
        or instant != _utc(claim.evaluated_at)
    ):
        return GroundingCode.DASHA_EVALUATION_MISMATCH

    facts = [item for item in dasha.facts if item.fact_id == claim.fact_id]
    if not facts:
        return GroundingCode.FACT_NOT_AUTHORIZED
    if len(facts) != 1:
        return GroundingCode.INVALID_EVIDENCE
    fact = facts[0]
    if not isinstance(fact, DashaActivePeriodFact):
        return GroundingCode.FACT_MISMATCH
    if fact.snapshot_id != snapshot.snapshot_id:
        return GroundingCode.SNAPSHOT_MISMATCH
    if _utc(fact.evaluated_at) != instant:
        return GroundingCode.DASHA_EVALUATION_MISMATCH
    if (
        fact.timeline_id != dasha.timeline_id
        or fact.method != dasha.method
        or fact.time_certainty != dasha.time_certainty
        or fact.is_conditional != dasha.is_conditional
        or dasha.profile_revision != snapshot.profile_revision
    ):
        return GroundingCode.INVALID_EVIDENCE

    active = dasha.lookup.periods
    chain = (active.mahadasha, active.antardasha, active.pratyantardasha)
    lower, upper = _utc(dasha.start_utc), _utc(dasha.end_utc_exclusive)
    birth = _utc(dasha.birth_utc)
    if lower is None or upper is None or birth is None or not lower <= birth <= instant < upper:
        return GroundingCode.INVALID_EVIDENCE
    parent_id = dasha.timeline_id
    for level, period in zip(("MD", "AD", "PD"), chain, strict=True):
        start, end = _utc(period.start_utc), _utc(period.end_utc_exclusive)
        if (
            period.level != level
            or period.period_id.rpartition(".")[0] != parent_id
            or start is None
            or end is None
            or not lower <= start <= instant < end <= upper
        ):
            return GroundingCode.INVALID_EVIDENCE
        lower, upper = start, end
        parent_id = period.period_id

    index = {"MD": 0, "AD": 1, "PD": 2}[claim.target.level]
    active_fact = context.dashas[index]
    if (
        fact.period != chain[index]
        or claim.period_id != fact.period.period_id
        or (claim.target.method, claim.target.lord, claim.target.parent_lord)
        != (active_fact.method, active_fact.lord, active_fact.parent_lord)
    ):
        return GroundingCode.FACT_MISMATCH
    return Search(
        query="",
        topics=("dasha",),
        languages=(evidence.language,),
        dashas=(active_fact,),
        evaluation=context.evaluation,
    )


def _fact_search(
    claim: FactClaim, snapshot: ChartSnapshotResponse, evidence: GroundingEvidence
) -> Search | GroundingCode:
    if snapshot.schema_version != 1 or snapshot.time_certainty not in (
        TimeCertainty.EXACT,
        TimeCertainty.APPROXIMATE,
    ):
        return GroundingCode.INVALID_EVIDENCE
    certainty = "approximate" if snapshot.time_certainty == TimeCertainty.APPROXIMATE else "exact"
    if claim.certainty != certainty:
        return GroundingCode.CERTAINTY_MISMATCH
    if isinstance(claim, ActiveDashaClaim):
        return _dasha_search(claim, snapshot, evidence)
    facts = [fact for fact in snapshot.chart.facts if fact.id == claim.fact_id]
    if not facts:
        return GroundingCode.FACT_NOT_AUTHORIZED
    if len(facts) != 1:
        return GroundingCode.INVALID_EVIDENCE
    fact = facts[0]
    if not isinstance(fact, ChartFactPlacement):
        return GroundingCode.FACT_MISMATCH
    return Search(
        query="",
        topics=(claim.target.topic,),
        languages=(evidence.language,),
        placements=(project_placement(fact, certainty),),
    )


def _match_index(matches: tuple[Match, ...]) -> dict[str, Match] | None:
    if len(matches) > 20:
        return None
    index: dict[str, Match] = {}
    for match in matches:
        if (
            not isinstance(match, Match)
            or match.citation_id in index
            or match.rights.status not in CLEARED
            or not match.content.strip()
            or match.applicability.topic != match.topic
            or match.citation_id.partition("/")[0] != f"{match.source_id}@{match.source_version}"
        ):
            return None
        index[match.citation_id] = match
    return index


def _validate_reading(reading: Reading, evidence: GroundingEvidence) -> GroundingResult:
    if reading.language != evidence.language:
        return GroundingResult(code=GroundingCode.LANGUAGE_MISMATCH)
    intent = evidence.intent
    abstentions = [claim for claim in reading.claims if isinstance(claim, Abstention)]
    if abstentions:
        expected = {
            "ambiguous": "ambiguous_request",
            "unsupported": "unsupported_request",
            "resolved": "insufficient_evidence",
        }[intent.status]
        if len(reading.claims) != 1 or reading.snapshot_id is not None:
            return GroundingResult(code=GroundingCode.MALFORMED_RESPONSE)
        if abstentions[0].reason != expected:
            return GroundingResult(code=GroundingCode.SCOPE_MISMATCH, claim_index=0)
        return GroundingResult(reading=reading)
    if intent.status != "resolved" or intent.scope is None or intent.intent is None:
        return GroundingResult(code=GroundingCode.SCOPE_MISMATCH)
    if intent.scope == "chart":
        if evidence.snapshot is None or reading.snapshot_id != evidence.snapshot.snapshot_id:
            return GroundingResult(code=GroundingCode.SNAPSHOT_MISMATCH)
        if not isinstance(evidence.snapshot, ChartSnapshotResponse):
            return GroundingResult(code=GroundingCode.BIRTH_TIME_UNSUPPORTED)
    elif reading.snapshot_id is not None:
        return GroundingResult(code=GroundingCode.SNAPSHOT_MISMATCH)
    matches = _match_index(evidence.matches)
    if matches is None:
        return GroundingResult(code=GroundingCode.INVALID_EVIDENCE)
    for index, claim in enumerate(reading.claims):
        assert not isinstance(claim, Abstention)
        code = _validate_claim(claim, intent, evidence, matches)
        if code is not None:
            return GroundingResult(code=code, claim_index=index)
    return GroundingResult(reading=reading)


def _validate_claim(
    claim: FactClaim | GeneralExplanation | Interpretation,
    intent: IntentResolution,
    evidence: GroundingEvidence,
    matches: dict[str, Match],
) -> GroundingCode | None:
    basis = claim.basis if isinstance(claim, Interpretation) else claim
    target = basis.target
    assert intent.intent is not None
    if isinstance(basis, GeneralExplanation):
        if intent.scope != "general":
            return GroundingCode.SCOPE_MISMATCH
        search = Search(query="", topics=(target.topic,), languages=(evidence.language,))
        conditional = False
    else:
        if intent.scope != "chart" or not isinstance(evidence.snapshot, ChartSnapshotResponse):
            return GroundingCode.SCOPE_MISMATCH
        fact_search = _fact_search(basis, evidence.snapshot, evidence)
        if isinstance(fact_search, GroundingCode):
            return fact_search
        search = fact_search
        supported = applicability_condition(target, search)
        if supported is None:
            return GroundingCode.FACT_MISMATCH
        conditional = supported
        if isinstance(claim, Interpretation) and (
            (claim.kind == "conditional_interpretation") != conditional
        ):
            return GroundingCode.CERTAINTY_MISMATCH
    if target not in intent.intent.targets:
        return GroundingCode.TARGET_MISMATCH
    if isinstance(claim, GeneralExplanation | Interpretation):
        match = matches.get(claim.citation_id)
        if match is None:
            return GroundingCode.CITATION_NOT_AUTHORIZED
        if (
            not matches_target(match.applicability, target)
            or applicability_condition(match.applicability, search) is not conditional
            or match.conditional != conditional
        ):
            return GroundingCode.CITATION_INAPPLICABLE
    return None


def validate_reading(payload: object, evidence: GroundingEvidence) -> GroundingResult:
    """Return validated selections or the first safe diagnostic, never partial output."""
    if not isinstance(payload, (str, bytes)):
        return GroundingResult(code=GroundingCode.MALFORMED_RESPONSE)
    if len(payload) > MAX_RESPONSE_BYTES:
        return GroundingResult(code=GroundingCode.RESPONSE_TOO_LARGE)
    try:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        if len(raw) > MAX_RESPONSE_BYTES:
            return GroundingResult(code=GroundingCode.RESPONSE_TOO_LARGE)
        json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
        reading = Reading.model_validate_json(raw, strict=True)
    except (ValueError, RecursionError):
        return GroundingResult(code=GroundingCode.MALFORMED_RESPONSE)
    try:
        return _validate_reading(reading, evidence)
    except (ValidationError, AttributeError, ValueError, OverflowError):
        return GroundingResult(code=GroundingCode.INVALID_EVIDENCE)
