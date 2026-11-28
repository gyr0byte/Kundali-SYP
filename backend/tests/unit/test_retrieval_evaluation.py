"""Local intent, ranking metrics, and an offline-only Vertex rehearsal."""

import json
import math
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.ai.embeddings import DIMENSION, normalize_vector
from app.ai.evaluate_retrieval import PilotRejected, PilotSettings, Usage, hosted_report
from app.ai.intent import intent_search, project_authorized_evidence, resolve_intent
from app.ai.retrieval_evaluation import (
    EvaluationRow,
    evaluate,
    keyword_comparisons,
    load_dataset,
    measure,
    prepare,
    semantic_fixture_rank,
)
from app.api.schemas.chart import ChartSnapshotResponse, MoonSnapshotResponse
from app.api.schemas.dasha import (
    ActiveDashaPeriods,
    DashaLookup,
    DashaPeriodBoundary,
    DashaResponse,
)
from app.calc.facts import ChartFactPlacement, ChartFacts
from app.db.models.profile import TimeCertainty
from app.knowledge.retrieval import retrieve


def test_multilingual_labels_and_equivalents() -> None:
    dataset, _ = load_dataset()
    canonical: dict[str, set[str]] = {}
    for row in prepare(dataset):
        case, result = row.case, row.resolution
        assert (result.status, result.scope) == (case.status, case.scope), case.id
        if result.intent is not None:
            assert result.intent.targets == (case.target,), case.id
            canonical.setdefault(case.group, set()).add(result.intent.encode())
        else:
            assert case.target is None
    assert len(dataset.cases) == 60
    assert len(canonical) == 10
    assert all(len(group) == 1 for group in canonical.values())


@pytest.mark.parametrize(
    ("question", "status"),
    [
        ("What is Cancer?", "ambiguous"),
        ("What is the Cancer sign?", "resolved"),
        ("चन्द्रमाको सामान्य अर्थ के हो?", "resolved"),
        ("मेरो कुण्डलीमा चन्द्रमा कुन भावमा छ?", "resolved"),
        ("Is my Moon in fifth or fourth house?", "ambiguous"),
        ("Moon in fifth house meaning?", "ambiguous"),
        ("My Moon in fourth house?", "unsupported"),
        ("My Venus in Rohini Nakshatra?", "unsupported"),
        ("My Moon in Rohini Pada 3?", "unsupported"),
        ("What does Rohini Nakshatra mean?", "unsupported"),
        ("What is my Moon? fixture@example.invalid", "unsupported"),
        ("What is my Moon? 2042-02-14", "unsupported"),
        ("?" * 301, "unsupported"),
    ],
)
def test_conservative_question_handling(question: str, status: str) -> None:
    dataset, _ = load_dataset()
    result = resolve_intent(question, dataset.charts["exact"].local_evidence())
    assert result.status == status
    if result.intent is None:
        assert result.reason


def test_projection_uses_snapshot_placements_and_matching_local_dasha_lookup() -> None:
    instant = datetime(2042, 1, 1, tzinfo=UTC)
    snapshot_id = UUID(int=10)
    fact = ChartFactPlacement.model_construct(
        planet="Moon", house=5, sign="Taurus", nakshatra="Rohini", pada=2
    )
    snapshot = ChartSnapshotResponse.model_construct(
        schema_version=1,
        time_certainty=TimeCertainty.APPROXIMATE,
        snapshot_id=snapshot_id,
        chart=ChartFacts.model_construct(chart_id="fixture-chart", facts=[fact]),
    )
    active = ActiveDashaPeriods(
        mahadasha=DashaPeriodBoundary.model_construct(level="MD", lord="Sun"),
        antardasha=DashaPeriodBoundary.model_construct(level="AD", lord="Venus"),
        pratyantardasha=DashaPeriodBoundary.model_construct(level="PD", lord="Moon"),
    )
    dasha = DashaResponse.model_construct(
        chart_id="fixture-chart",
        snapshot_id=snapshot_id,
        time_certainty="approximate",
        is_conditional=True,
        method="vimshottari-v1",
        lookup=DashaLookup(status="active", as_of=instant, periods=active),
    )
    data = project_authorized_evidence(snapshot, dasha, current_at=instant)
    assert data.placements[0].certainty == "approximate"
    assert len(data.dashas) == 3
    assert data.dashas[1].parent_lord == "Sun"
    result = resolve_intent("What is my current AD?", data)
    assert result.intent is not None
    payload = json.loads(result.intent.encode())
    assert payload == {
        "topic": "dasha",
        "method": "vimshottari-v1",
        "level": "AD",
        "lord": "Venus",
        "parent_lord": "Sun",
    }
    historical = project_authorized_evidence(snapshot, dasha)
    assert resolve_intent("What is my current AD?", historical).status == "unsupported"
    assert resolve_intent("Which is my AD?", historical).status == "resolved"
    other = dasha.model_copy(update={"snapshot_id": UUID(int=11)})
    assert not project_authorized_evidence(snapshot, other).dashas
    mismatch = replace(
        data, evaluation=data.evaluation.model_copy(update={"snapshot_id": UUID(int=11)})
    )
    assert resolve_intent("Which is my AD?", mismatch).status == "unsupported"
    moon_only = MoonSnapshotResponse.model_construct(schema_version=2)
    assert not project_authorized_evidence(moon_only, dasha).placements
    assert not project_authorized_evidence(moon_only, dasha).dashas


def test_metrics_distinguish_misses_rank_and_leakage() -> None:
    dataset, _ = load_dataset()
    moon, other = (
        next(row for row in prepare(dataset) if row.case.id == name)
        for name in ("moon-general-en", "unknown-time-en")
    )
    rows = (
        EvaluationRow(moon, ("moon-index", "moon-en", "pending-moon", "sun-en", "moon-ne"), 2.0),
        EvaluationRow(other, ("sun-en",), 8.0),
    )
    result = measure(rows, {"moon-index", "moon-en", "moon-ne", "sun-en"})
    assert result["intent_accuracy"] == 1
    assert result["recall_at_1"] == 0
    assert result["recall_at_5"] == 1
    assert result["mrr_at_5"] == 0.5
    assert result["ndcg_at_5"] == pytest.approx(
        (1 / math.log2(3) + 1 / math.log2(6)) / (1 + 1 / math.log2(3)), abs=1e-6
    )
    assert result["applicability_violations"] == 2
    assert result["publication_leaks"] == 1
    assert result["unsupported_abstention_accuracy"] == 0
    assert result["retrieval_p95_ms"] == 8.0


def test_keyword_variants_and_approximate_gate() -> None:
    dataset, _ = load_dataset()
    cases = prepare(dataset)
    reports = keyword_comparisons(dataset, cases)
    assert reports["original"]["overall"]["recall_at_5"] == 0.6
    assert reports["canonical"]["overall"]["recall_at_5"] == 1
    for report in reports.values():
        assert report["overall"]["publication_leaks"] == 0
        assert report["overall"]["applicability_violations"] == 0
    case = next(row for row in cases if row.case.id == "approximate-house-en")
    assert case.resolution.intent is not None
    search = intent_search(case.resolution.intent, case.evidence, query="Moon 5")
    assert search.targets == (case.case.target,)

    def check(session, search, prepared):
        matches = retrieve(session, search)
        assert len(matches) == 1
        assert matches[0].conditional
        return matches

    evaluate(dataset, (case,), check)


def test_semantic_pipeline_with_controlled_vectors_and_tier_toggle() -> None:
    dataset, _ = load_dataset()
    case = next(row for row in prepare(dataset) if row.case.id == "moon-general-en")

    def unit(x: float, y: float = 0) -> tuple[float, ...]:
        return normalize_vector([x, y] + [0] * (DIMENSION - 2))

    vectors = {
        "moon-ne": unit(1),
        "moon-en": unit(0.995, math.sqrt(1 - 0.995**2)),
        "moon-index": unit(0, 1),
        **{
            key: unit(1)
            for key in (
                "pending-moon",
                "disabled-moon",
                "withdrawn-moon",
                "test-moon",
                "unresolved-moon",
                "sun-en",
            )
        },
    }

    def check(session, search, prepared):
        no_overlap = search.model_copy(update={"query": "sphinx"})
        assert not retrieve(session, no_overlap)
        unbiased = semantic_fixture_rank(session, no_overlap, unit(1), vectors, tier2_bonus=0)
        weighted = semantic_fixture_rank(session, no_overlap, unit(1), vectors, tier2_bonus=0.01)
        assert [row.source_id for row in unbiased] == ["moon-ne", "moon-en", "moon-index"]
        assert [row.source_id for row in weighted] == ["moon-en", "moon-ne", "moon-index"]
        return weighted

    evaluate(dataset, (case,), check)


def _pilot() -> PilotSettings:
    _, digest = load_dataset()
    return PilotSettings(True, digest, "fixture-project", "us-central1", 44, 7000, 150)


def test_hosted_approval_and_preflight_precede_authentication() -> None:
    def no_auth() -> str:
        pytest.fail("Provider authentication must not run")

    for settings, reason in [
        (replace(_pilot(), authorized=False), "explicit authorization"),
        (replace(_pilot(), approved_digest="0" * 64), "checksum"),
        (replace(_pilot(), max_attempts=43), "budgets"),
        (replace(_pilot(), max_spend_microusd=6599), "budgets"),
        (replace(_pilot(), price_per_1000_microusd=0), "positive"),
    ]:
        with pytest.raises(PilotRejected, match=reason):
            hosted_report(settings, no_auth)
    usage = Usage(replace(_pilot(), max_attempts=1, max_spend_microusd=150))
    with pytest.raises(PilotRejected, match="spending"):
        usage.attempt(1001)
    usage.attempt(1000)
    with pytest.raises(PilotRejected, match="request"):
        usage.attempt(1)


def test_mock_vertex_receives_only_evaluation_passages_and_deduplicated_intents() -> None:
    dataset, _ = load_dataset()
    allowed_text = {row.text for row in dataset.passages if row.state == "approved"}
    allowed_queries = {
        row.resolution.intent.encode() for row in prepare(dataset) if row.resolution.intent
    }
    sent: list[tuple[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["parameters"] == {"outputDimensionality": DIMENSION, "autoTruncate": False}
        (instance,) = payload["instances"]
        sent.append((instance["task_type"], instance["content"]))
        if len(sent) == 1:
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "embeddings": {
                            "values": [1] + [0] * (DIMENSION - 1),
                            "statistics": {"token_count": 8},
                        }
                    }
                ]
            },
        )

    result, complete = hosted_report(
        _pilot(), lambda: "synthetic-test-token", transport=httpx.MockTransport(handle)
    )
    assert complete
    assert [value for task, value in sent if task == "RETRIEVAL_DOCUMENT"][0] == sent[1][1]
    assert {value for task, value in sent if task == "RETRIEVAL_DOCUMENT"} == allowed_text
    queries = [value for task, value in sent if task == "RETRIEVAL_QUERY"]
    assert len(queries) == len(allowed_queries) == 9
    assert set(queries) == allowed_queries
    assert result["usage"] == {
        "attempts": 23,
        "estimated_microusd": 3450,
        "usage_reports": 22,
        "reported_tokens": 176,
        "failed_attempts": 1,
    }
    assert result["semantic"]["no_tier_bonus"]["overall"]["publication_leaks"] == 0
    export = json.dumps(result)
    for item in ("synthetic-test-token", "fixture-project", "2042-01-01", "Ignore instructions"):
        assert item not in export
    assert not any(row.text in export for row in dataset.passages)


def test_hosted_failure_stops_and_withholds_incomplete_semantic_metrics() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="provider response detail must not appear")

    report, complete = hosted_report(
        _pilot(), lambda: "synthetic-test-token", transport=httpx.MockTransport(handle)
    )
    assert not complete
    assert report["semantic"] is None
    assert report["usage"]["failed_attempts"] == 2
    assert len(report["requests"]) == 1
    assert "provider response detail" not in json.dumps(report)
