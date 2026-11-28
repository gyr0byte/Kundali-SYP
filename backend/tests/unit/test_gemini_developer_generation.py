"""Synthetic-only evaluation and mocked Gemini generateContent transport."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app.ai import generation_pilot_fixture
from app.ai.evaluate_generation import offline_baseline
from app.ai.gemini_developer_generation import (
    _ACTIVE_CASE,
    MAX_INPUT_BYTES,
    MAX_RESPONSE_BYTES,
    MODEL,
    HostedAuthorization,
    _CaseProvider,
    _PilotBudget,
    _ProviderError,
    run_hosted_pilot,
)
from app.ai.generation_pilot_fixture import FIXTURE_SHA256, PilotRejected, load_fixture, run_case
from app.ai.llm_adapter import GenerationRequest

_LEGACY = "AIza" + "a" * 35
_MODERN = "AQ." + "b" * 50
_APPROVED = HostedAuthorization(True, True, FIXTURE_SHA256, 8)
_PRIVATE = "mock-private-response-value"
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def _response(text='{"choices":[1]}', *, finish="STOP"):
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": finish}
        ],
        "usageMetadata": {
            "promptTokenCount": 100,
            "candidatesTokenCount": 7,
            "totalTokenCount": 107,
        },
        "modelVersion": MODEL,
        "responseId": _PRIVATE,
    }


def _run(handler, *, approval=_APPROVED, key=_MODERN):
    return asyncio.run(
        run_hosted_pilot(
            approval,
            lambda: key,
            transport=httpx.MockTransport(handler),
        )
    )


@pytest.mark.parametrize("key", [_LEGACY, _MODERN])
def test_pinned_pilot_sends_only_the_allowed_rest_payload(key):
    fixture = load_fixture()
    reviewed = [case for case in fixture.cases if case.offers]
    sent = []

    def transport(request):
        case = reviewed[len(sent)]
        sent.append(request)
        assert request.method == "POST" and str(request.url) == _URL
        assert request.headers["x-goog-api-key"] == key
        assert "authorization" not in request.headers and not request.url.query
        assert len(request.content) <= MAX_INPUT_BYTES
        data = json.loads(request.content)
        assert set(data) == {"systemInstruction", "contents", "generationConfig"}
        (message,) = data["contents"]
        assert message["role"] == "user"
        (part,) = message["parts"]
        assert json.loads(part["text"]) == {
            "language": case.language,
            "options": [
                {
                    "number": item.number,
                    "kind": item.kind,
                    "target": item.target.model_dump(
                        mode="json",
                        exclude_none=True,
                    ),
                }
                for item in case.choices()
            ],
        }
        config = data["generationConfig"]
        assert set(config) == {
            "candidateCount",
            "maxOutputTokens",
            "thinkingConfig",
            "responseMimeType",
            "responseJsonSchema",
        }
        assert config["candidateCount"] == 1 and config["maxOutputTokens"] == 256
        assert config["thinkingConfig"] == {"includeThoughts": False, "thinkingLevel": "MINIMAL"}
        assert config["responseMimeType"] == "application/json"
        assert config["responseJsonSchema"] == {
            "type": "object",
            "required": ["choices"],
            "additionalProperties": False,
            "properties": {
                "choices": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": len(case.offers),
                    "items": {"type": "integer", "minimum": 1, "maximum": len(case.offers)},
                }
            },
        }
        outbound = request.content.decode()
        for private in [
            key,
            case.question,
            "2042-01-01",
            "f_moon",
            "synthetic-generation@1",
            *(passage.text for passage in fixture.passages),
        ]:
            assert private not in outbound
        return httpx.Response(200, json=_response())

    report = _run(transport, key=key)
    assert report["http_attempts"] == len(sent) == 4
    assert report["estimated_cost_usd"] == 0
    assert report["summary"]["selection_accuracy"] == 1
    assert report["summary"]["grounding_and_safety_accepted"] == 4
    assert report["summary"]["abstentions"] == 3
    assert report["summary"]["cases_evaluated"] == 7
    assert report["stop_reason"] is None and not report["skipped_cases"]
    assert report["attempts"][0]["tokens"]["totalTokenCount"] == 107
    assert all(row["generation_attempts"] == 0 for row in report["summary"]["cases"][4:])
    assert _PRIVATE not in json.dumps(report) and key not in json.dumps(report)


def test_local_baseline_is_deterministic_in_outcome():
    baseline = asyncio.run(offline_baseline())
    assert baseline["http_attempts"] == 0
    assert baseline["summary"]["selection_accuracy"] == 1
    assert baseline["summary"]["grounding_and_safety_accepted"] == 4
    assert baseline["summary"]["abstentions"] == 3
    assert all(row["matches_label"] for row in baseline["summary"]["cases"])


@pytest.mark.parametrize(
    "settings",
    [
        replace(_APPROVED, authorized=False),
        replace(_APPROVED, confirm_free_tier=False),
        replace(_APPROVED, approved_fixture_sha256="0" * 64),
        replace(_APPROVED, max_http_attempts=21),
        replace(_APPROVED, max_http_attempts=0),
    ],
)
def test_hosted_gates_refuse_before_reading_a_key_or_calling_http(settings):
    with pytest.raises(PilotRejected):
        asyncio.run(
            run_hosted_pilot(
                settings,
                lambda: pytest.fail("Credential access"),
                transport=httpx.MockTransport(lambda _: pytest.fail("HTTP dispatch")),
            )
        )


def test_pinned_manifest_cannot_be_replaced_with_caller_content(tmp_path, monkeypatch):
    changed = tmp_path / "changed.json"
    changed.write_text('{"private":"real-input"}', encoding="utf-8")
    monkeypatch.setattr(generation_pilot_fixture, "_FIXTURE", changed)
    with pytest.raises(PilotRejected, match="checksum"):
        asyncio.run(
            run_hosted_pilot(
                _APPROVED,
                lambda: pytest.fail("Credential access"),
                transport=httpx.MockTransport(lambda _: pytest.fail("HTTP dispatch")),
            )
        )


def test_even_identical_chart_concept_outside_synthetic_scope_cannot_dispatch():
    async def exercise():
        case = load_fixture().cases[0]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: pytest.fail("HTTP dispatch"))
        ) as client:
            provider = _CaseProvider(
                case,
                object(),
                _PilotBudget(8),
                client,
                asyncio.Semaphore(1),
                lambda: pytest.fail("Credential access"),
            )
            deadline = asyncio.get_running_loop().time() + 5
            request = GenerationRequest(case.language, case.choices(), deadline=deadline)
            with pytest.raises(_ProviderError, match="^unauthorized_input$"):
                await provider.generate(request)
            with pytest.raises(_ProviderError, match="^unauthorized_input$"):
                await provider._post(False, deadline)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (401, "authentication_failed"),
        (403, "authentication_failed"),
        (429, "quota_exhausted"),
    ],
)
def test_auth_and_quota_errors_stop_the_pilot_and_discard_error_bodies(status, outcome):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, text=_PRIVATE + _MODERN)

    result = _run(handler)
    assert result["http_attempts"] == len(calls) == 1
    assert result["stop_reason"] == outcome
    assert result["attempts"][0]["outcome"] == outcome
    assert result["summary"]["correction_attempts"] == 0
    assert len(result["skipped_cases"]) == 6
    assert _PRIVATE not in json.dumps(result) and _MODERN not in json.dumps(result)


def test_invalid_key_never_dispatches():
    result = _run(lambda _: pytest.fail("HTTP dispatch"), key="invalid\nsecret")
    assert result["stop_reason"] == "authentication_failed" and result["http_attempts"] == 0


@pytest.mark.parametrize(
    ("response", "outcome"),
    [
        (httpx.Response(503, text=_PRIVATE), "http_error"),
        (httpx.Response(302, headers={"Location": "https://example.invalid"}), "http_error"),
        (
            httpx.Response(200, content=b"{", headers={"Content-Type": "application/json"}),
            "invalid_envelope",
        ),
        (httpx.Response(200, json={"candidates": []}), "invalid_envelope"),
        (httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}), "blocked"),
        (httpx.Response(200, json=_response("", finish="MAX_TOKENS")), "truncated"),
        (httpx.Response(200, json=_response('{"choices":[1]}', finish="SAFETY")), "blocked"),
        (
            httpx.Response(200, json=_response(finish="MALFORMED_FUNCTION_CALL")),
            "unexpected_finish",
        ),
        (httpx.Response(200, json=_response("  ")), "invalid_envelope"),
        (
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "STOP",
                            "content": {
                                "role": "model",
                                "parts": [{"functionCall": {"name": _PRIVATE}}],
                            },
                        }
                    ]
                },
            ),
            "invalid_envelope",
        ),
        (httpx.Response(200, json=_response("x" * 1100)), "response_too_large"),
        (httpx.Response(200, json=_response("x" * MAX_RESPONSE_BYTES)), "response_too_large"),
    ],
)
def test_bad_envelopes_finish_reasons_server_errors_and_redirects_have_no_retry(response, outcome):
    def handler(request):
        assert str(request.url) == _URL
        return response

    result = _run(handler, approval=replace(_APPROVED, max_http_attempts=1))
    assert result["http_attempts"] == 1 and result["attempts"][0]["outcome"] == outcome
    assert result["summary"]["correction_attempts"] == 0
    assert result["summary"]["grounding_and_safety_accepted"] == 0
    assert _PRIVATE not in json.dumps(result)


def test_reported_implicit_cache_use_stops_the_pilot():
    body = _response()
    body["usageMetadata"]["cachedContentTokenCount"] = 5
    result = _run(lambda _: httpx.Response(200, json=body))
    assert result["http_attempts"] == 1 and result["stop_reason"] == "cache_use_reported"
    assert result["summary"]["grounding_and_safety_accepted"] == 0


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ('{"choices":[42]}', "unauthorized_choice"),
        ('{"choices":[1],"answer":"' + _PRIVATE + '"}', "output_policy_violation"),
    ],
)
def test_inner_json_remains_subject_to_existing_grounding_and_safety(text, code):
    result = _run(lambda _: httpx.Response(200, json=_response(text)))
    assert result["http_attempts"] == 4 and result["summary"]["correction_attempts"] == 0
    assert all(row["failure"] == code for row in result["summary"]["cases"][:4])
    assert _PRIVATE not in json.dumps(result)


@pytest.mark.parametrize("max_calls", [1, 8])
def test_malformed_numeric_choice_uses_one_full_correction_and_obeys_global_cap(max_calls):
    bodies = []

    def handler(request):
        bodies.append(json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"]))
        return httpx.Response(
            200, json=_response('{"choices":[1' if len(bodies) <= 2 else '{"choices":[1]}')
        )

    result = _run(handler, approval=replace(_APPROVED, max_http_attempts=max_calls))
    assert len(bodies) == result["http_attempts"] == (1 if max_calls == 1 else 5)
    assert result["summary"]["correction_attempts"] == 1
    assert result["summary"]["cases"][0]["generation_attempts"] == 2
    assert not result["summary"]["cases"][0]["accepted"]
    assert "correction" not in bodies[0]
    if max_calls == 1:
        assert result["stop_reason"] == "budget_exhausted"
    else:
        assert bodies[1] == {**bodies[0], "correction": "malformed_selection"}
        assert "correction" not in bodies[2]  # Next case, never a third dispatch on first.


@pytest.mark.parametrize(
    ("error", "outcome", "fallback"),
    [
        (httpx.ReadTimeout(_PRIVATE), "timeout", "provider_timeout"),
        (httpx.ConnectError(_PRIVATE), "transport_error", "provider_failure"),
    ],
)
def test_transport_failures_are_sanitized_and_never_retried(error, outcome, fallback):
    def handler(_):
        raise error

    result = _run(handler, approval=replace(_APPROVED, max_http_attempts=1))
    assert result["attempts"][0]["outcome"] == outcome and result["http_attempts"] == 1
    assert result["summary"]["cases"][0]["fallback"] == fallback
    assert result["summary"]["correction_attempts"] == 0
    assert _PRIVATE not in json.dumps(result)


def test_caller_cancellation_reaches_async_transport():
    async def exercise():
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def handler(_):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

        task = asyncio.create_task(
            run_hosted_pilot(
                _APPROVED,
                lambda: _MODERN,
                transport=httpx.MockTransport(handler),
            )
        )
        await asyncio.wait_for(started.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cancelled.wait(), 1)

    asyncio.run(exercise())


def test_orchestrator_passes_the_same_absolute_deadline_to_both_invocations():
    requests = []

    class Provider:
        async def generate(self, request):
            assert request.deadline is not None
            assert asyncio.get_running_loop().time() < request.deadline
            requests.append(request)
            return "{}" if len(requests) == 1 else '{"choices":[1]}'

    fixture = load_fixture()
    result = asyncio.run(run_case(fixture, fixture.cases[0], Provider()))
    assert result.claims and len(requests) == 2
    assert requests[0].deadline == requests[1].deadline


def test_http_body_read_stops_at_the_orchestration_deadline():
    async def exercise():
        cancelled = asyncio.Event()

        class HangingBody(httpx.AsyncByteStream):
            async def __aiter__(self):
                try:
                    yield b"{"
                    await asyncio.Future()
                finally:
                    cancelled.set()

        def handler(_):
            return httpx.Response(
                200, headers={"Content-Type": "application/json"}, stream=HangingBody()
            )

        fixture = load_fixture()
        case = fixture.cases[0]
        budget = _PilotBudget(8)
        permit = object()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _CaseProvider(
                case, permit, budget, client, asyncio.Semaphore(1), lambda: _MODERN
            )
            token = _ACTIVE_CASE.set(permit)
            try:
                result = await run_case(fixture, case, provider, timeout_seconds=0.05)
                await asyncio.wait_for(cancelled.wait(), 1)
            finally:
                _ACTIVE_CASE.reset(token)
        assert result.fallback == "provider_timeout" and result.attempts == 1
        assert len(budget.attempts) == 1 and budget.attempts[0].http_status == 200
        assert budget.attempts[0].outcome in {"timeout", "cancelled"}

    asyncio.run(exercise())


def test_valid_correction_is_grounded_and_compared_with_the_baseline():
    payloads = iter(
        ["{}", '{"choices":[1]}', '{"choices":[2]}', '{"choices":[1]}', '{"choices":[1]}']
    )
    result = _run(lambda _: httpx.Response(200, json=_response(next(payloads))))
    assert result["status"] == "complete"
    assert result["http_cases_attempted"] == 4 and result["http_attempts"] == 5
    assert result["http_corrections"] == 1
    assert result["summary"]["selection_accuracy"] == 1
    assert result["summary"]["cases"][1]["selection"] == (2,)
