"""Read-only orchestration for the authenticated, locally selected assistant."""

import asyncio
from datetime import UTC
from unicodedata import category
from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.generation import generate_reading
from app.ai.guardrails import SafetyAction, assess_input
from app.ai.intent import (
    AuthorizedEvidence,
    canonical_keyword_text,
    intent_search,
    project_authorized_evidence,
    question_options,
    resolve_intent,
)
from app.ai.local_selector import LocalSelector
from app.ai.rendering import (
    FallbackCode,
    PassageApproval,
    disclaimer_text,
    fallback_text,
    passage_approval,
)
from app.ai.schemas import Locale
from app.ai.validator import GroundingEvidence
from app.api.schemas.chart import ChartSnapshotResponse
from app.api.schemas.chat import (
    ChatCitation,
    ChatClaim,
    ChatRequest,
    ChatResponse,
    ChatSnapshotContext,
)
from app.calc.dasha import DashaInputError
from app.core.clock import Clock
from app.core.config import Settings
from app.knowledge.retrieval import Evaluation, Match, Search, current_matches, rank_keyword
from app.services.chart_service import get_chart_snapshot, get_owned_snapshot_revisions
from app.services.dasha_service import derive_snapshot_dasha

_MAX_APPROVALS = 64
_MAX_PASSAGE_CHARS = 1200
_MAX_RETRIEVED = 6
_MAX_CHART_FACTS = 16


def get_chat_passage_approvals() -> frozenset[PassageApproval]:
    """Server-controlled exact-text approvals. The initial deployment has none."""
    return frozenset()


def chat_fallback(
    language: Locale, outcome: FallbackCode, snapshot: ChatSnapshotContext | None = None
) -> ChatResponse:
    return ChatResponse(
        language=language,
        outcome=outcome,
        answer=fallback_text(outcome, language),
        disclaimer=None if outcome == FallbackCode.CRISIS_SUPPORT else disclaimer_text(language),
        snapshot=snapshot,
    )


def _safe_label(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not 1 <= len(value) <= 250 or any(category(char) in {"Cc", "Cf", "Cs"} for char in value):
        return None
    return value


def _public_citation(match: Match) -> ChatCitation | None:
    title = _safe_label(match.bibliography.get("title"))
    attribution = _safe_label(match.rights.attribution)
    if title is None or attribution is None:
        return None
    return ChatCitation.model_validate(
        {
            "citation_id": match.citation_id,
            "source_version": match.source_version,
            "language": match.language,
            "tier": match.tier,
            "title": title,
            "author": _safe_label(match.bibliography.get("author")),
            "edition": _safe_label(match.bibliography.get("edition")),
            "chapter": _safe_label(match.locator.get("chapter")),
            "page": _safe_label(match.locator.get("page")),
            "verse": _safe_label(match.locator.get("verse")),
            "attribution": attribution,
        }
    )


def _retrieve(
    db: Session, search: Search, approvals: frozenset[PassageApproval]
) -> tuple[Match, ...]:
    ids = tuple(sorted({approval.citation_id for approval in approvals}))
    candidates = current_matches(db, search, citation_ids=ids, max_content_chars=_MAX_PASSAGE_CHARS)
    return rank_keyword(
        search, (match for match in candidates if passage_approval(match) in approvals)
    )


def respond_to_chat(
    db: Session,
    request: ChatRequest,
    *,
    owner_id: UUID,
    settings: Settings,
    clock: Clock,
    approvals: frozenset[PassageApproval],
) -> ChatResponse | None:
    """Return None for missing or non-owned snapshots, including those deleted mid-request."""
    language = request.language
    snapshot_id = request.snapshot_id
    policy = assess_input(request.question)
    options = question_options(request.question) if policy.action == SafetyAction.ALLOWED else None
    snapshot = None
    if snapshot_id is not None:
        if options is not None and options.chart_scoped:
            snapshot = get_chart_snapshot(db, snapshot_id, owner_id=owner_id, app_settings=settings)
            if snapshot is None:
                return None
        elif get_owned_snapshot_revisions(db, snapshot_id, owner_id=owner_id) is None:
            return None

    if options is not None and options.chart_scoped and snapshot is None:
        return chat_fallback(language, FallbackCode.SNAPSHOT_REQUIRED)
    if isinstance(snapshot, ChartSnapshotResponse) and len(snapshot.chart.facts) > _MAX_CHART_FACTS:
        return chat_fallback(language, FallbackCode.GROUNDING_FAILED)
    if len(approvals) > _MAX_APPROVALS:
        approvals = frozenset()

    evaluated_at = None
    evaluation = None
    dasha = None
    if options is not None and options.active_dasha and isinstance(snapshot, ChartSnapshotResponse):
        # Release the authentication/snapshot transaction before local computation.
        db.rollback()
        evaluated_at = clock.now().astimezone(UTC)
        try:
            dasha = derive_snapshot_dasha(snapshot, evaluated_at)
        except DashaInputError:
            return chat_fallback(language, FallbackCode.DASHA_UNAVAILABLE)
        if dasha.lookup.status != "active":
            return chat_fallback(language, FallbackCode.DASHA_UNAVAILABLE)
        evaluation = Evaluation(snapshot_id=snapshot.snapshot_id, instant=evaluated_at)

    authorized = (
        project_authorized_evidence(snapshot, dasha, current_at=evaluated_at)
        if snapshot is not None
        else AuthorizedEvidence()
    )
    intent = resolve_intent(request.question, authorized)
    mode = options.mode if options is not None else "interpretation"
    search = None
    matches: tuple[Match, ...] = ()
    if options is not None and intent.intent is not None and mode == "interpretation" and approvals:
        search = intent_search(
            intent.intent,
            authorized,
            query=canonical_keyword_text(intent.intent),
            limit=_MAX_RETRIEVED,
        )
        matches = _retrieve(db, search, approvals)

    target = intent.intent.targets[0] if intent.intent is not None else None
    evidence = GroundingEvidence(intent, language, snapshot, dasha, evaluation, matches)
    db.rollback()
    # This service runs on FastAPI's synchronous route worker. DB work stays on that worker.
    result = asyncio.run(
        generate_reading(
            request.question,
            evidence,
            LocalSelector(target, matches),
            approvals=approvals,
            mode=mode,
            current_at=evaluated_at,
        )
    )

    context = None
    if snapshot is not None:
        revisions = get_owned_snapshot_revisions(db, snapshot.snapshot_id, owner_id=owner_id)
        if revisions is None:
            return None
        saved, current = revisions
        if saved != snapshot.profile_revision:
            return chat_fallback(language, FallbackCode.GROUNDING_FAILED)
        context = ChatSnapshotContext(
            snapshot_id=snapshot.snapshot_id,
            is_current_profile_revision=saved == current,
            time_certainty=snapshot.time_certainty,
        )
    if result.fallback is not None:
        return chat_fallback(language, result.fallback, context)
    if len(result.claims) != 1:
        return chat_fallback(language, FallbackCode.GROUNDING_FAILED, context)

    claim = result.claims[0]
    citations: tuple[ChatCitation, ...] = ()
    if claim.citation_id is not None:
        if search is None:
            return chat_fallback(language, FallbackCode.GROUNDING_FAILED, context)
        original = next(
            (match for match in matches if match.citation_id == claim.citation_id), None
        )
        # A fresh SELECT refreshes ORM objects and checks the current published source and chunk.
        latest = next(
            current_matches(
                db,
                search,
                citation_ids=(claim.citation_id,),
                max_content_chars=_MAX_PASSAGE_CHARS,
            ),
            None,
        )
        if latest is None or latest != original or passage_approval(latest) not in approvals:
            return chat_fallback(language, FallbackCode.INSUFFICIENT_KNOWLEDGE, context)
        citation = _public_citation(latest)
        if citation is None:
            return chat_fallback(language, FallbackCode.INSUFFICIENT_KNOWLEDGE, context)
        citations = (citation,)
    return ChatResponse(
        language=language,
        outcome="answered",
        answer=f"{claim.text}\n\n{claim.passage}" if claim.passage is not None else claim.text,
        claims=(
            ChatClaim(
                kind=claim.kind,
                target=claim.target,
                text=claim.text,
                conditional=claim.conditional,
                citation_id=claim.citation_id,
            ),
        ),
        citations=citations,
        disclaimer=result.disclaimer,
        snapshot=context,
        evaluated_at=evaluated_at if claim.target.topic == "dasha" else None,
    )
