"""Offline Developer API transport and free-tier evaluation safeguards."""

import json
from dataclasses import replace

import httpx
import pytest

from app.ai.embeddings import DIMENSION, EmbeddingQuery, EmbeddingUnavailable, InvalidEmbedding
from app.ai.evaluate_retrieval import PilotRejected, PilotSettings, hosted_report
from app.ai.gemini_developer_embeddings import GeminiDeveloperEmbeddings
from app.ai.gemini_embeddings import VertexGeminiEmbeddings
from app.ai.retrieval_evaluation import load_dataset, prepare
from app.ai.vector_store import build_identity

_KEY = "AIza" + "x" * 35
_AUTH_KEY = "AQ." + "x" * 50


def _settings() -> PilotSettings:
    return PilotSettings(True, load_dataset()[1], "", "", 44, 0, 0, "developer", True)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"authorized": False}, "authorization"),
        ({"confirm_free_tier": False}, "free-tier"),
        ({"approved_digest": "0" * 64}, "checksum"),
        ({"max_attempts": 45}, "44 attempts"),
        ({"max_attempts": 43}, "bounded retry plan"),
        ({"max_spend_microusd": 1}, "zero-cost"),
        ({"price_per_1000_microusd": 1}, "zero-cost"),
        ({"project": "paid-project"}, "zero-cost"),
    ],
)
def test_free_tier_gates_precede_key_access(overrides, message) -> None:
    def unexpected() -> str:
        pytest.fail("The key must not be read")

    with pytest.raises(PilotRejected, match=message):
        hosted_report(replace(_settings(), **overrides), unexpected)


@pytest.mark.parametrize("key", [_KEY, _AUTH_KEY])
def test_pilot_sends_only_the_reviewed_fixture_and_canonical_queries(key: str) -> None:
    dataset, _ = load_dataset()
    documents = {row.text for row in dataset.passages if row.state == "approved"}
    queries = {row.resolution.intent.encode() for row in prepare(dataset) if row.resolution.intent}
    sent: list[tuple[str, str]] = []

    def reply(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"
        )
        assert request.headers["x-goog-api-key"] == key
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        text = body["content"]["parts"][0]["text"]
        assert body == {
            "model": "models/gemini-embedding-001",
            "outputDimensionality": 384,
            "taskType": body["taskType"],
            "content": {"parts": [{"text": text}]},
        }
        sent.append((body["taskType"], text))
        if len(sent) == 1:
            return httpx.Response(503)
        payload = {"embedding": {"values": [5] + [0] * (DIMENSION - 1)}}
        if len(sent) == 2:
            payload["usageMetadata"] = {"promptTokenCount": 8}
        return httpx.Response(200, json=payload)

    report, complete = hosted_report(_settings(), lambda: key, transport=httpx.MockTransport(reply))
    assert complete and len(sent) == 23 and sent[0] == sent[1]
    assert set(sent) == (
        {("RETRIEVAL_DOCUMENT", text) for text in documents}
        | {("RETRIEVAL_QUERY", text) for text in queries}
    )
    assert report["usage"]["estimated_microusd"] == 0
    assert report["usage"]["reported_tokens"] == 8
    assert report["usage"]["usage_reports"] == 1
    assert report["requests"][0]["attempt_details"][0]["outcome"] == "transient_http"
    assert key not in json.dumps(report)


@pytest.mark.parametrize(
    "key",
    [
        " " + _KEY,
        _AUTH_KEY + "\n",
        _AUTH_KEY + "\0",
        "AQ.." + "x" * 49,
        "AQ." + "x" * 16,
        "AIza" + "x" * 34,
        "x" * 53,
    ],
)
def test_malformed_credentials_are_rejected_before_transport(key: str) -> None:
    developer = GeminiDeveloperEmbeddings(
        lambda: key,
        approved_documents=frozenset({"reviewed"}),
        approved_queries=frozenset(),
        on_attempt=lambda _: pytest.fail("Invalid credential reached the transport"),
        on_attempt_result=lambda *_: None,
        on_usage=lambda _: None,
        transport=httpx.MockTransport(lambda _: pytest.fail("Unexpected request")),
    )
    with pytest.raises(EmbeddingUnavailable, match="authentication is unavailable"):
        developer.embed_document("reviewed")


def test_quota_exhaustion_stops_without_retry_or_provider_fallback() -> None:
    requests = []

    def unavailable(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, text=_KEY)

    report, complete = hosted_report(
        _settings(), lambda: _KEY, transport=httpx.MockTransport(unavailable)
    )
    assert not complete and len(requests) == 1
    assert report["requests"][0]["attempt_details"][0]["outcome"] == "quota_exhausted"
    assert report["semantic"] is None
    assert _KEY not in json.dumps(report)


@pytest.mark.parametrize("values", [[1], [0] * DIMENSION, [float("inf")] * DIMENSION])
def test_vector_validation_and_adapter_allowlist(values) -> None:
    key_reads = []
    developer = GeminiDeveloperEmbeddings(
        lambda: key_reads.append(True) or _KEY,
        approved_documents=frozenset({"reviewed"}),
        approved_queries=frozenset(),
        on_attempt=lambda _: None,
        on_attempt_result=lambda *_: None,
        on_usage=lambda _: None,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=json.dumps({"embedding": {"values": values}}))
        ),
    )
    with pytest.raises(InvalidEmbedding, match="outside"):
        developer.embed_document("unreviewed")
    with pytest.raises(InvalidEmbedding, match="outside"):
        developer.embed_query(
            EmbeddingQuery.model_validate(
                {"targets": [{"topic": "planet_general", "planet": "Moon"}]}
            )
        )
    assert not key_reads
    with pytest.raises(InvalidEmbedding):
        developer.embed_document("reviewed")

    vertex = VertexGeminiEmbeddings("fixture-project", "us-central1", lambda: _KEY)
    assert developer.config.provider != vertex.config.provider
    assert build_identity(developer.config, "production", 1) != build_identity(
        vertex.config, "production", 1
    )
