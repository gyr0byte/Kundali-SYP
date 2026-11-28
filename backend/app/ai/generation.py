"""Bounded selection, grounding and trusted rendering for one request."""

import asyncio
import json
import math
import re
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import ValidationError

from app.ai.guardrails import SafetyAction, SafetyDecision, assess_input, passage_is_safe
from app.ai.intent import AuthorizedEvidence, project_authorized_evidence, resolve_intent
from app.ai.llm_adapter import (
    MALFORMED_SELECTION_CORRECTION,
    ClaimChoice,
    GenerationAbstained,
    GenerationProvider,
    GenerationRequest,
)
from app.ai.rendering import (
    FallbackCode,
    PassageApproval,
    RenderedClaim,
    disclaimer_text,
    fallback_text,
    passage_approval,
    render_claim,
)
from app.ai.schemas import Abstention, Claim, Interpretation, Locale
from app.ai.validator import (
    GroundingCode,
    GroundingEvidence,
    ResponseDecodeError,
    decode_response,
    validate_reading,
)
from app.api.schemas.chart import ChartSnapshotResponse, MoonSnapshotResponse
from app.api.schemas.dasha import DashaActivePeriodFact
from app.calc.facts import ChartFactPlacement
from app.db.models.profile import TimeCertainty
from app.knowledge.chunking import (
    Applicability,
    DashaRule,
    NakshatraRule,
    PadaRule,
    PlanetInHouse,
    PlanetInSign,
)
from app.knowledge.retrieval import matches_target

_MAX_OPTIONS = 12


class GenerationCode(StrEnum):
    MALFORMED_SELECTION = "malformed_selection"
    OUTPUT_POLICY_VIOLATION = "output_policy_violation"
    UNAUTHORIZED_CHOICE = "unauthorized_choice"
    RESPONSE_TOO_LARGE = "response_too_large"
    UNSAFE_PASSAGE = "unsafe_passage"
    GROUNDING_REJECTED = "grounding_rejected"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    language: Locale
    policy: SafetyDecision
    attempts: int
    claims: tuple[RenderedClaim, ...] = ()
    disclaimer: str | None = None
    fallback: FallbackCode | None = None
    message: str | None = None
    failure: GenerationCode | None = None
    grounding_code: GroundingCode | None = None
    selected_options: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Failure:
    code: FallbackCode
    failure: GenerationCode | None = None
    grounding: GroundingCode | None = None


def _reading(claims: list[dict[str, object]], evidence: GroundingEvidence) -> str:
    snapshot = (
        str(evidence.snapshot.snapshot_id)
        if evidence.snapshot is not None and evidence.intent.scope == "chart"
        else None
    )
    return json.dumps(
        {
            "schema_version": 1,
            "language": evidence.language,
            "snapshot_id": snapshot,
            "claims": claims,
        }
    )


def _fact_candidate(target: Applicability, evidence: GroundingEvidence) -> dict[str, object] | None:
    snapshot = evidence.snapshot
    if not isinstance(snapshot, ChartSnapshotResponse):
        return None
    certainty = "approximate" if snapshot.time_certainty == TimeCertainty.APPROXIMATE else "exact"
    common = {"target": target.model_dump(mode="json"), "certainty": certainty}
    if isinstance(target, DashaRule):
        if evidence.dasha is None or evidence.evaluation is None:
            return None
        dasha = [
            fact
            for fact in evidence.dasha.facts
            if isinstance(fact, DashaActivePeriodFact) and fact.period.level == target.level
        ]
        if len(dasha) != 1:
            return None
        return {
            **common,
            "kind": "dasha_fact",
            "fact_id": dasha[0].fact_id,
            "period_id": dasha[0].period.period_id,
            "evaluated_at": evidence.evaluation.instant.isoformat(),
        }
    if isinstance(target, (PlanetInHouse, PlanetInSign)):
        planet = target.planet
    elif isinstance(target, (NakshatraRule, PadaRule)):
        planet = target.body
    else:
        return None
    facts = [
        fact
        for fact in snapshot.chart.facts
        if isinstance(fact, ChartFactPlacement) and fact.planet == planet
    ]
    if len(facts) != 1:
        return None
    return {**common, "kind": "chart_fact", "fact_id": facts[0].id}


def _failure_for_grounding(code: GroundingCode | None) -> _Failure:
    return _Failure(FallbackCode.GROUNDING_FAILED, GenerationCode.GROUNDING_REJECTED, code)


def _prepare_choices(
    evidence: GroundingEvidence,
    approvals: frozenset[PassageApproval],
    mode: Literal["interpretation", "facts"],
) -> tuple[Claim, ...] | _Failure:
    intent = evidence.intent
    assert intent.intent is not None and len(intent.intent.targets) == 1
    target = intent.intent.targets[0]
    if intent.scope == "chart":
        basis = _fact_candidate(target, evidence)
        if basis is None:
            return _failure_for_grounding(GroundingCode.FACT_NOT_AUTHORIZED)
        checked = validate_reading(_reading([basis], evidence), evidence)
        if checked.reading is None:
            return _failure_for_grounding(checked.code)
        if mode == "facts":
            return checked.reading.claims
    else:
        basis = None

    choices: list[Claim] = []
    for match in evidence.matches:
        if (
            not matches_target(match.applicability, target)
            or passage_approval(match) not in approvals
        ):
            continue
        claim: dict[str, object] = {"citation_id": match.citation_id}
        if basis is None:
            claim.update(kind="general_explanation", target=target.model_dump(mode="json"))
        else:
            claim.update(
                kind="conditional_interpretation"
                if basis["certainty"] == "approximate"
                else "interpretation",
                basis=basis,
            )
        checked = validate_reading(_reading([claim], evidence), evidence)
        if checked.reading is None:
            return _failure_for_grounding(checked.code)
        if not passage_is_safe(match.content):
            return _Failure(FallbackCode.RESTRICTED_REQUEST, GenerationCode.UNSAFE_PASSAGE)
        if len(choices) < _MAX_OPTIONS:
            choices.append(checked.reading.claims[0])
    return tuple(choices) if choices else _Failure(FallbackCode.INSUFFICIENT_KNOWLEDGE)


def _select(payload: object, count: int) -> tuple[int, ...] | GenerationCode:
    try:
        _, value = decode_response(payload)
    except ResponseDecodeError as exc:
        if exc.code == GroundingCode.RESPONSE_TOO_LARGE:
            return GenerationCode.RESPONSE_TOO_LARGE
        # Correction is limited to truncation or syntax mistakes in the numeric envelope.
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        if isinstance(text, str) and re.fullmatch(
            r'\{(?:"choices")?[:\[\],0-9-]*\}?', "".join(text.split())
        ):
            return GenerationCode.MALFORMED_SELECTION
        return GenerationCode.OUTPUT_POLICY_VIOLATION
    if not isinstance(value, dict) or value.keys() - {"choices"}:
        return GenerationCode.OUTPUT_POLICY_VIOLATION
    choices = value.get("choices")
    if choices is None:
        return GenerationCode.MALFORMED_SELECTION
    if not isinstance(choices, list) or any(type(choice) is not int for choice in choices):
        return GenerationCode.OUTPUT_POLICY_VIOLATION
    if any(not 1 <= choice <= count for choice in choices):
        return GenerationCode.UNAUTHORIZED_CHOICE
    if not choices or len(choices) != len(set(choices)):
        return GenerationCode.MALFORMED_SELECTION
    return tuple(choices)


def _provider_choices(options: tuple[Claim, ...]) -> tuple[ClaimChoice, ...]:
    choices = []
    for number, claim in enumerate(options, 1):
        assert not isinstance(claim, Abstention)
        target = claim.basis.target if isinstance(claim, Interpretation) else claim.target
        choices.append(ClaimChoice(number, claim.kind, target))
    return tuple(choices)


def _drain(task: asyncio.Task[str | bytes]) -> None:
    if not task.cancelled():
        task.exception()


def _cancel(task: asyncio.Task[str | bytes]) -> None:
    task.cancel()
    task.add_done_callback(_drain)


async def _ask(
    provider: GenerationProvider,
    request: GenerationRequest,
    deadline: float,
) -> str | bytes | FallbackCode:
    loop = asyncio.get_running_loop()
    remaining = deadline - loop.time()
    if remaining <= 0:
        return FallbackCode.PROVIDER_TIMEOUT
    try:
        task = asyncio.create_task(provider.generate(request))
    except Exception:
        return FallbackCode.PROVIDER_FAILURE
    try:
        done, _ = await asyncio.wait((task,), timeout=remaining)
    except asyncio.CancelledError:
        _cancel(task)
        raise
    if not done or loop.time() > deadline:
        _cancel(task)
        return FallbackCode.PROVIDER_TIMEOUT
    if task.cancelled():
        return FallbackCode.PROVIDER_FAILURE
    try:
        return task.result()
    except GenerationAbstained:
        return FallbackCode.INSUFFICIENT_KNOWLEDGE
    except TimeoutError:
        return FallbackCode.PROVIDER_TIMEOUT
    except Exception:
        return FallbackCode.PROVIDER_FAILURE


async def generate_reading(
    question: str,
    evidence: GroundingEvidence,
    provider: GenerationProvider,
    *,
    approvals: frozenset[PassageApproval] = frozenset(),
    mode: Literal["interpretation", "facts"] = "interpretation",
    current_at: datetime | None = None,
    timeout_seconds: float = 8.0,
) -> GenerationResult:
    language = evidence.language
    policy = assess_input(question)
    disclaimer = disclaimer_text(language)
    attempts = 0

    def fallback(
        code: FallbackCode,
        failure: GenerationCode | None = None,
        grounding: GroundingCode | None = None,
    ) -> GenerationResult:
        return GenerationResult(
            language,
            policy,
            attempts,
            fallback=code,
            message=fallback_text(code, language),
            disclaimer=None if code == FallbackCode.CRISIS_SUPPORT else disclaimer,
            failure=failure,
            grounding_code=grounding,
        )

    if policy.action == SafetyAction.CRISIS:
        return fallback(FallbackCode.CRISIS_SUPPORT)
    if policy.action != SafetyAction.ALLOWED:
        return fallback(
            FallbackCode.UNSUPPORTED_REQUEST
            if policy.action == SafetyAction.ABSTAIN
            else FallbackCode.RESTRICTED_REQUEST
        )

    try:
        authorized = (
            project_authorized_evidence(evidence.snapshot, evidence.dasha, current_at=current_at)
            if evidence.snapshot is not None
            else AuthorizedEvidence()
        )
        intent = resolve_intent(question, authorized)
        if intent.status != "resolved":
            return fallback(
                FallbackCode.UNCERTAIN_BIRTH_TIME
                if intent.reason == "authorized_evidence_unavailable"
                and isinstance(evidence.snapshot, MoonSnapshotResponse)
                else FallbackCode.UNSUPPORTED_REQUEST
            )
        if intent != evidence.intent:
            return fallback(
                FallbackCode.GROUNDING_FAILED,
                GenerationCode.GROUNDING_REJECTED,
                GroundingCode.TARGET_MISMATCH,
            )
        options = _prepare_choices(evidence, approvals, mode)
    except (ValidationError, AttributeError, ValueError, OverflowError):
        return fallback(
            FallbackCode.GROUNDING_FAILED,
            GenerationCode.GROUNDING_REJECTED,
            GroundingCode.INVALID_EVIDENCE,
        )
    if isinstance(options, _Failure):
        return fallback(options.code, options.failure, options.grounding)

    if not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
        raise ValueError("Generation timeout must be between zero and thirty seconds")
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    request = GenerationRequest(language, _provider_choices(options), deadline=deadline)
    for attempt in range(2):
        if asyncio.get_running_loop().time() >= deadline:
            return fallback(FallbackCode.PROVIDER_TIMEOUT)
        attempts += 1
        payload = await _ask(provider, request, deadline)
        if isinstance(payload, FallbackCode):
            return fallback(payload)
        selected = _select(payload, len(options))
        if isinstance(selected, GenerationCode):
            if attempt == 0 and selected == GenerationCode.MALFORMED_SELECTION:
                request = replace(
                    request,
                    correction=MALFORMED_SELECTION_CORRECTION,
                )
                continue
            return fallback(FallbackCode.GROUNDING_FAILED, selected)

        final = validate_reading(
            _reading(
                [options[number - 1].model_dump(mode="json") for number in selected], evidence
            ),
            evidence,
        )
        if final.reading is None:
            return fallback(
                FallbackCode.GROUNDING_FAILED, GenerationCode.GROUNDING_REJECTED, final.code
            )
        rendered = []
        passages = {item.citation_id: item for item in evidence.matches}
        for claim in final.reading.claims:
            assert not isinstance(claim, Abstention)
            item = render_claim(claim, language, passages, approvals)
            if item is None:
                return fallback(FallbackCode.RESTRICTED_REQUEST, GenerationCode.UNSAFE_PASSAGE)
            rendered.append(item)
        return GenerationResult(
            language, policy, attempts, tuple(rendered), disclaimer, selected_options=selected
        )
    raise AssertionError("Generation attempts exhausted")
