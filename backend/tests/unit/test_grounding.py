"""Offline grounding tests using synthetic snapshots and retrieval rows."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.ai.embeddings import EmbeddingQuery
from app.ai.intent import (
    AuthorizedEvidence,
    IntentResolution,
    intent_search,
    project_authorized_evidence,
    resolve_intent,
)
from app.ai.validator import (
    MAX_RESPONSE_BYTES,
    GroundingCode,
    GroundingEvidence,
    validate_reading,
)
from app.api.schemas.chart import ChartSnapshotResponse, MoonSnapshotResponse
from app.api.schemas.dasha import DashaActivePeriodFact
from app.calc.facts import ChartFactPlacement, ChartFacts, ChartMetadata, ChartSettings
from app.db.models.knowledge import KnowledgeChunk, KnowledgeSource
from app.db.models.profile import TimeCertainty
from app.knowledge.retrieval import Evaluation, match_candidate, validated_citation
from app.services.dasha_service import derive_snapshot_dasha
from tests.knowledge_fixtures import payload as knowledge_fixture

SNAPSHOT_ID = UUID(int=9)
BIRTH = datetime(2000, 4, 28, 9, 50, tzinfo=UTC)
AT = BIRTH + timedelta(days=1090, microseconds=123456)
MOON_HOUSE = {"topic": "planet_in_house", "planet": "Moon", "house": 5}
MOON_GENERAL = {"topic": "planet_general", "planet": "Moon"}


def _snapshot(certainty=TimeCertainty.EXACT):
    moon = ChartFactPlacement(
        id="f_moon",
        planet="Moon",
        house=5,
        sign="Taurus",
        sign_index=1,
        longitude=46.0,
        degree=16.0,
        nakshatra="Rohini",
        pada=2,
        speed=12.0,
        retrograde=False,
    )
    venus = moon.model_copy(
        update={
            "id": "f_venus",
            "planet": "Venus",
            "house": 4,
            "sign": "Aries",
            "nakshatra": "Ashwini",
            "pada": 1,
        }
    )
    chart = ChartFacts(
        chart_id="fixture-chart",
        engine_version="test",
        settings=ChartSettings(),
        facts=[moon, venus],
        metadata=ChartMetadata(
            ephemeris_source="swieph",
            julian_day=2451662.0,
            utc_offset_hours=0,
            datetime_utc_iso=BIRTH.isoformat(),
        ),
    )
    return ChartSnapshotResponse.model_construct(
        chart=chart,
        snapshot_id=SNAPSHOT_ID,
        schema_version=1,
        profile_revision=2,
        is_current_profile_revision=True,
        time_certainty=certainty,
    )


def _intent(target, *, scope="chart"):
    return IntentResolution(
        "resolved",
        scope=scope,
        intent=EmbeddingQuery.model_validate(
            {
                "targets": [target],
            }
        ),
    )


def _chart_claim(target=MOON_HOUSE, *, fact_id="f_moon", certainty="exact"):
    return {"kind": "chart_fact", "fact_id": fact_id, "target": target, "certainty": certainty}


def _response(*claims, language="en", snapshot_id=SNAPSHOT_ID):
    return json.dumps(
        {
            "schema_version": 1,
            "language": language,
            "claims": claims,
            "snapshot_id": str(snapshot_id) if snapshot_id is not None else None,
        }
    )


def _rows(target):
    fixture = knowledge_fixture()
    release = fixture["source"]
    source = KnowledgeSource(
        source_id=release["source_id"],
        version=1,
        tier=3,
        enabled=True,
        collection="production",
        rights_status="project_owned",
        rights=release["rights"],
        publication_review="offline fixture",
        bibliography={"title": release["title"]},
    )
    chunk = KnowledgeChunk(
        citation_id="fixture-corpus@1/concept@1",
        source_id=source.source_id,
        source_version=1,
        language="ne",
        tradition="fixture",
        topic=target["topic"],
        content="चन्द्रमाको परिचय।",
        applicability=target,
        locator={"page": "fixture"},
        editorial_status="approved",
        editorial_review="offline fixture",
    )
    return chunk, source


def _match(evidence, target, *, use_request_target=True):
    assert evidence.intent.intent is not None
    query = intent_search(
        evidence.intent.intent if use_request_target else _intent(target).intent,
        project_authorized_evidence(evidence.snapshot, evidence.dasha)
        if evidence.snapshot
        else AuthorizedEvidence(),
        query="",
        languages=("en", "ne"),
    )
    match = match_candidate(*_rows(target), query)
    assert match is not None
    return match


@pytest.mark.parametrize(
    "target",
    [
        MOON_HOUSE,
        {"topic": "planet_in_sign", "planet": "Moon", "sign": "Taurus"},
        {"topic": "nakshatra", "body": "Moon", "nakshatra": "Rohini"},
        {"topic": "pada", "body": "Moon", "nakshatra": "Rohini", "pada": 2},
    ],
)
def test_accepts_chart_claims_with_current_snapshot_and_one_fact(target):
    evidence = GroundingEvidence(_intent(target), "en", _snapshot())
    result = validate_reading(_response(_chart_claim(target)), evidence)
    assert result.code is None and result.reading is not None


@pytest.mark.parametrize(
    ("claim", "code"),
    [
        (_chart_claim(fact_id="f_invented"), GroundingCode.FACT_NOT_AUTHORIZED),
        (_chart_claim(fact_id="f_venus"), GroundingCode.FACT_MISMATCH),
        (_chart_claim({**MOON_HOUSE, "house": 4}), GroundingCode.FACT_MISMATCH),
        (
            _chart_claim({"topic": "planet_in_sign", "planet": "Moon", "sign": "Aries"}),
            GroundingCode.FACT_MISMATCH,
        ),
        (
            _chart_claim({"topic": "nakshatra", "body": "Moon", "nakshatra": "Ashwini"}),
            GroundingCode.FACT_MISMATCH,
        ),
        (
            _chart_claim({"topic": "pada", "body": "Moon", "nakshatra": "Rohini", "pada": 1}),
            GroundingCode.FACT_MISMATCH,
        ),
        (
            _chart_claim({"topic": "planet_in_sign", "planet": "Moon", "sign": "Taurus"}),
            GroundingCode.TARGET_MISMATCH,
        ),
    ],
)
def test_rejects_invented_composed_and_off_topic_chart_claims(claim, code):
    result = validate_reading(
        _response(claim), GroundingEvidence(_intent(MOON_HOUSE), "en", _snapshot())
    )
    assert result.model_dump(mode="json") == {"reading": None, "code": code.value, "claim_index": 0}


def test_reading_is_bound_to_snapshot_even_when_the_fact_id_is_the_same():
    other = _snapshot().model_copy(update={"snapshot_id": UUID(int=99)})
    evidence = GroundingEvidence(_intent(MOON_HOUSE), "en", other)
    assert (
        validate_reading(_response(_chart_claim()), evidence).code
        == GroundingCode.SNAPSHOT_MISMATCH
    )


@pytest.mark.parametrize("language", ["en", "ne"])
def test_general_explanation_can_select_a_trusted_passage_in_either_response_locale(language):
    question = "What is Moon?" if language == "en" else "चन्द्रमा के हो?"
    evidence = GroundingEvidence(resolve_intent(question), language)
    match = _match(evidence, MOON_GENERAL)
    claim = {
        "kind": "general_explanation",
        "target": MOON_GENERAL,
        "citation_id": match.citation_id,
    }
    result = validate_reading(
        _response(claim, language=language, snapshot_id=None),
        replace(
            evidence,
            matches=(match,),
        ),
    )
    assert result.reading is not None
    assert result.reading.language == language
    assert not hasattr(result.reading.claims[0], "text")


def test_conditional_interpretation_and_source_applicability():
    snapshot = _snapshot(TimeCertainty.APPROXIMATE)
    evidence = GroundingEvidence(_intent(MOON_HOUSE), "en", snapshot)
    match = _match(evidence, MOON_HOUSE)
    basis = _chart_claim(certainty="approximate")
    claim = {"kind": "conditional_interpretation", "basis": basis, "citation_id": match.citation_id}
    assert validate_reading(_response(claim), replace(evidence, matches=(match,))).reading
    result = validate_reading(
        _response({**claim, "kind": "interpretation"}),
        replace(
            evidence,
            matches=(match,),
        ),
    )
    assert result.code == GroundingCode.CERTAINTY_MISMATCH
    assert (
        validate_reading(_response(_chart_claim()), evidence).code
        == GroundingCode.CERTAINTY_MISMATCH
    )

    venus_house = {"topic": "planet_in_house", "planet": "Venus", "house": 4}
    other = _match(evidence, venus_house, use_request_target=False)
    result = validate_reading(_response(claim), replace(evidence, matches=(other,)))
    assert result.code == GroundingCode.CITATION_INAPPLICABLE
    assert (
        validate_reading(_response(claim), evidence).code == GroundingCode.CITATION_NOT_AUTHORIZED
    )
    forged = {**claim, "citation_id": "fixture-corpus@1/invented@1"}
    assert (
        validate_reading(
            _response(forged),
            replace(
                evidence,
                matches=(match,),
            ),
        ).code
        == GroundingCode.CITATION_NOT_AUTHORIZED
    )


def _dasha_case(level, certainty=TimeCertainty.EXACT):
    snapshot = _snapshot(certainty)
    dasha = derive_snapshot_dasha(snapshot, AT)
    assert dasha.lookup.periods is not None
    facts = [f for f in dasha.facts if isinstance(f, DashaActivePeriodFact)]
    fact = next(f for f in facts if f.period.level == level)
    periods = dasha.lookup.periods
    parent = {"MD": None, "AD": periods.mahadasha.lord, "PD": periods.antardasha.lord}[level]
    target = {
        "topic": "dasha",
        "method": dasha.method,
        "level": level,
        "lord": fact.period.lord,
        "parent_lord": parent,
    }
    claim = {
        "kind": "dasha_fact",
        "fact_id": fact.fact_id,
        "period_id": fact.period.period_id,
        "evaluated_at": AT.isoformat(),
        "target": target,
        "certainty": certainty.value,
    }
    evidence = GroundingEvidence(
        _intent(target),
        "en",
        snapshot,
        dasha,
        Evaluation(
            snapshot_id=SNAPSHOT_ID,
            instant=AT,
        ),
    )
    return claim, evidence


@pytest.mark.parametrize("level", ["MD", "AD", "PD"])
def test_active_dasha_claims_and_parent_agnostic_citation(level):
    claim, evidence = _dasha_case(level)
    assert validate_reading(_response(claim), evidence).reading
    match = _match(evidence, {**claim["target"], "parent_lord": None})
    interpretation = {"kind": "interpretation", "basis": claim, "citation_id": match.citation_id}
    assert validate_reading(_response(interpretation), replace(evidence, matches=(match,))).reading


def test_dasha_rejects_wrong_lord_parent_period_instant_and_foreign_snapshot():
    claim, evidence = _dasha_case("AD")
    for field in ("lord", "parent_lord"):
        bad = "Ketu" if claim["target"][field] != "Ketu" else "Rahu"
        payload = _response({**claim, "target": {**claim["target"], field: bad}})
        assert validate_reading(payload, evidence).code == GroundingCode.FACT_MISMATCH
    assert (
        validate_reading(_response({**claim, "period_id": "invented"}), evidence).code
        == GroundingCode.FACT_MISMATCH
    )
    wrong_instant = AT + timedelta(microseconds=1)
    assert (
        validate_reading(
            _response({**claim, "evaluated_at": wrong_instant.isoformat()}), evidence
        ).code
        == GroundingCode.DASHA_EVALUATION_MISMATCH
    )
    assert (
        validate_reading(
            _response(claim),
            replace(
                evidence,
                evaluation=Evaluation(snapshot_id=SNAPSHOT_ID, instant=wrong_instant),
            ),
        ).code
        == GroundingCode.DASHA_EVALUATION_MISMATCH
    )
    assert evidence.dasha is not None
    other = evidence.dasha.model_copy(update={"snapshot_id": UUID(int=100)})
    assert (
        validate_reading(
            _response(claim),
            replace(
                evidence,
                dasha=other,
            ),
        ).code
        == GroundingCode.SNAPSHOT_MISMATCH
    )
    facts = [
        fact.model_copy(update={"snapshot_id": UUID(int=100)})
        if fact.fact_id == claim["fact_id"]
        else fact
        for fact in evidence.dasha.facts
    ]
    assert (
        validate_reading(
            _response(claim),
            replace(
                evidence,
                dasha=evidence.dasha.model_copy(update={"facts": facts}),
            ),
        ).code
        == GroundingCode.SNAPSHOT_MISMATCH
    )


def test_approximate_dasha_interpretation_is_conditional():
    basis, evidence = _dasha_case("AD", TimeCertainty.APPROXIMATE)
    match = _match(evidence, basis["target"])
    evidence = replace(evidence, matches=(match,))
    claim = {"basis": basis, "citation_id": match.citation_id}
    assert validate_reading(
        _response({**claim, "kind": "conditional_interpretation"}), evidence
    ).reading
    assert (
        validate_reading(_response({**claim, "kind": "interpretation"}), evidence).code
        == GroundingCode.CERTAINTY_MISMATCH
    )


def test_active_lookup_cannot_contain_a_period_at_its_exclusive_end():
    claim, evidence = _dasha_case("AD")
    assert evidence.dasha is not None
    lookup = evidence.dasha.lookup
    assert lookup.periods is not None
    active = lookup.periods
    invalid = active.pratyantardasha.model_copy(update={"end_utc_exclusive": AT})
    periods = active.model_copy(update={"pratyantardasha": invalid})
    dasha = evidence.dasha.model_copy(
        update={"lookup": lookup.model_copy(update={"periods": periods})}
    )
    assert (
        validate_reading(_response(claim), replace(evidence, dasha=dasha)).code
        == GroundingCode.INVALID_EVIDENCE
    )


def test_a_later_invalid_claim_rejects_the_entire_reading():
    evidence = GroundingEvidence(_intent(MOON_HOUSE), "en", _snapshot())
    response = _response(_chart_claim(), _chart_claim(fact_id="f_unknown"))
    result = validate_reading(response, evidence)
    assert result.reading is None
    assert result.code == GroundingCode.FACT_NOT_AUTHORIZED
    assert result.claim_index == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("enabled", False),
        ("editorial_status", "pending"),
        ("rights_status", "excluded"),
        ("rights_status", "unresolved"),
        ("collection", "test"),
        ("publication_review", None),
    ],
)
def test_unpublished_rows_never_become_retrieval_evidence(field, value):
    chunk, source = _rows(MOON_GENERAL)
    setattr(chunk if field == "editorial_status" else source, field, value)
    intent = resolve_intent("What is Moon?")
    search = intent_search(
        intent.intent,
        project_authorized_evidence(
            MoonSnapshotResponse.model_construct(schema_version=2),
        ),
        query="Moon",
    )
    assert match_candidate(chunk, source, search) is None


def test_historical_citation_cannot_substitute_for_current_match():
    chunk, source = _rows(MOON_GENERAL)
    source.enabled = False
    citation = validated_citation(chunk, source)
    assert citation is not None
    evidence = GroundingEvidence(resolve_intent("What is Moon?"), "en", matches=(citation,))
    claim = {
        "kind": "general_explanation",
        "target": MOON_GENERAL,
        "citation_id": citation.citation_id,
    }
    assert (
        validate_reading(_response(claim, snapshot_id=None), evidence).code
        == GroundingCode.INVALID_EVIDENCE
    )


def test_unknown_time_cannot_supply_houses_or_dasha_and_can_abstain():
    unknown = MoonSnapshotResponse.model_construct(schema_version=2, snapshot_id=SNAPSHOT_ID)
    dasha_claim, dasha_evidence = _dasha_case("AD")
    for claim, intent in (
        (_chart_claim(), _intent(MOON_HOUSE)),
        (dasha_claim, dasha_evidence.intent),
    ):
        evidence = GroundingEvidence(intent, "en", unknown)
        assert (
            validate_reading(_response(claim), evidence).code
            == GroundingCode.BIRTH_TIME_UNSUPPORTED
        )
    intent = resolve_intent("Which house is my Moon in?", project_authorized_evidence(unknown))
    claim = {"kind": "abstention", "reason": "unsupported_request"}
    assert validate_reading(
        _response(claim, snapshot_id=None),
        GroundingEvidence(
            intent,
            "en",
            unknown,
        ),
    ).reading


def test_abstention_with_empty_corpus_and_general_chart_scope_separation():
    evidence = GroundingEvidence(resolve_intent("What is Moon?"), "en", _snapshot())
    claim = {
        "kind": "general_explanation",
        "target": MOON_GENERAL,
        "citation_id": "fixture-corpus@1/concept@1",
    }
    abstention = {"kind": "abstention", "reason": "insufficient_evidence"}
    assert (
        validate_reading(_response(claim, snapshot_id=None), evidence).code
        == GroundingCode.CITATION_NOT_AUTHORIZED
    )
    assert validate_reading(_response(abstention, snapshot_id=None), evidence).reading
    assert (
        validate_reading(_response(_chart_claim(), snapshot_id=None), evidence).code
        == GroundingCode.SCOPE_MISMATCH
    )
    assert (
        validate_reading(
            _response(claim),
            replace(
                evidence,
                intent=_intent(MOON_HOUSE),
            ),
        ).code
        == GroundingCode.SCOPE_MISMATCH
    )
    assert (
        validate_reading(_response(abstention, claim, snapshot_id=None), evidence).code
        == GroundingCode.MALFORMED_RESPONSE
    )


@pytest.mark.parametrize(
    "request_text",
    [
        "arbitrary Nepali or English prose",
        '{"schema_version":1,"schema_version":1,"language":"en","claims":[]}',
        _response({**_chart_claim(), "text": "An invented prediction"}),
        _response({**_chart_claim(), "fact_id": "not a fact"}),
        _response({**_chart_claim(), "target": {**MOON_HOUSE, "house": "5"}}),
        _response({**_chart_claim(), "target": {**MOON_HOUSE, "house": True}}),
        _response(*[_chart_claim()] * 13),
        _response({"kind": "summary", "text": "Ignored structure"}),
        _response(_chart_claim()).replace(
            '"language": "en"', '"language": "en", "summary": "prose"'
        ),
        _response(_chart_claim()).replace('"schema_version": 1', '"schema_version": true'),
        _response(
            {"kind": "general_explanation", "target": MOON_GENERAL, "citation_id": "invalid"}
        ),
        b"\xff",
        {"schema_version": 1, "summary": "bypass the JSON contract"},
        None,
    ],
)
def test_malformed_and_prose_bypass_are_rejected(request_text):
    result = validate_reading(
        request_text, GroundingEvidence(_intent(MOON_HOUSE), "en", _snapshot())
    )
    assert result.model_dump(mode="json") == {
        "reading": None,
        "code": "malformed_response",
        "claim_index": None,
    }


def test_response_size_is_bounded_in_bytes_and_language_is_request_scoped():
    evidence = GroundingEvidence(_intent(MOON_HOUSE), "en", _snapshot())
    assert (
        validate_reading("x" * (MAX_RESPONSE_BYTES + 1), evidence).code
        == GroundingCode.RESPONSE_TOO_LARGE
    )
    assert (
        validate_reading("क" * MAX_RESPONSE_BYTES, evidence).code
        == GroundingCode.RESPONSE_TOO_LARGE
    )
    assert (
        validate_reading(_response(_chart_claim(), language="ne"), evidence).code
        == GroundingCode.LANGUAGE_MISMATCH
    )
