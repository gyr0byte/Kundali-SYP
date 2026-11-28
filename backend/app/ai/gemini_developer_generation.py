"""Gemini Developer API transport confined to the pinned synthetic pilot."""

import asyncio
import math
import re
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from time import perf_counter

import httpx

from app.ai.gemini_developer_auth import developer_api_key
from app.ai.generation_pilot_fixture import (
    FIXTURE_SHA256,
    PilotCase,
    PilotFixture,
    PilotRejected,
    describe_case,
    load_fixture,
    run_case,
    summarize,
)
from app.ai.llm_adapter import MALFORMED_SELECTION_CORRECTION, GenerationRequest
from app.ai.validator import ResponseDecodeError, decode_response
from app.knowledge.provenance import canonical_bytes

MODEL = "gemini-3.5-flash-lite"
MAX_HTTP_ATTEMPTS = 20
MAX_INPUT_BYTES = 1536
MAX_RESPONSE_BYTES = 16 * 1024
MAX_SELECTION_BYTES = 1024
MAX_OUTPUT_TOKENS = 256
THINKING_LEVEL = "MINIMAL"
_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
_SYSTEM = (
    "Select exactly one offered option for this synthetic evaluation. "
    "Return only JSON containing a choices array of offered integers. "
    "Use the first suitable option when the options are equivalent."
)
_ACTIVE_CASE: ContextVar[object | None] = ContextVar("gemini_synthetic_case", default=None)


class _Code(StrEnum):
    UNAUTHORIZED_INPUT = "unauthorized_input"
    BUDGET_EXHAUSTED = "budget_exhausted"
    AUTHENTICATION = "authentication_failed"
    QUOTA = "quota_exhausted"
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    INVALID_ENVELOPE = "invalid_envelope"
    BLOCKED = "blocked"
    TRUNCATED = "truncated"
    UNEXPECTED_FINISH = "unexpected_finish"
    RESPONSE_TOO_LARGE = "response_too_large"
    CACHE_USE_REPORTED = "cache_use_reported"
    OK = "ok"


class _ProviderError(RuntimeError):
    def __init__(self, code: _Code) -> None:
        super().__init__(code.value)
        self.code = code


@dataclass(frozen=True, slots=True)
class HostedAuthorization:
    authorized: bool
    confirm_free_tier: bool
    approved_fixture_sha256: str
    max_http_attempts: int

    def load(self) -> PilotFixture:
        if self.authorized is not True or self.confirm_free_tier is not True:
            raise PilotRejected(
                "Explicit hosted authorization and disabled-billing confirmation required"
            )
        if (
            type(self.max_http_attempts) is not int
            or not 1 <= self.max_http_attempts <= MAX_HTTP_ATTEMPTS
        ):
            raise PilotRejected("Pilot budget must be between 1 and 20 HTTP attempts")
        if self.approved_fixture_sha256 != FIXTURE_SHA256:
            raise PilotRejected("The reviewed fixture checksum is required")
        return load_fixture(self.approved_fixture_sha256)


@dataclass(slots=True)
class _Attempt:
    case_id: str
    correction: bool
    http_status: int | None = None
    outcome: _Code = _Code.INVALID_ENVELOPE
    latency_ms: float = 0
    tokens: dict[str, int] = field(default_factory=dict)
    model_version: str | None = None


@dataclass(slots=True)
class _PilotBudget:
    limit: int
    attempts: list[_Attempt] = field(default_factory=list)
    stop: _Code | None = None

    def reserve(self, case_id: str, correction: bool) -> _Attempt:
        if self.stop is not None:
            raise _ProviderError(self.stop)
        if len(self.attempts) >= self.limit:
            self.stop = _Code.BUDGET_EXHAUSTED
            raise _ProviderError(self.stop)
        attempt = _Attempt(case_id, correction)
        self.attempts.append(attempt)
        return attempt


def _payload(case: PilotCase, correction: bool) -> bytes:
    # Serialize only the pinned fixture's typed options, never the caller's object.
    options = [
        {
            "number": offer.number,
            "kind": offer.kind,
            "target": offer.target.model_dump(mode="json", exclude_none=True),
        }
        for offer in case.choices()
    ]
    prompt: dict[str, object] = {"language": case.language, "options": options}
    if correction:
        prompt["correction"] = MALFORMED_SELECTION_CORRECTION.code
    body = canonical_bytes(
        {
            "systemInstruction": {"parts": [{"text": _SYSTEM}]},
            "contents": [{"role": "user", "parts": [{"text": canonical_bytes(prompt).decode()}]}],
            "generationConfig": {
                "candidateCount": 1,
                "maxOutputTokens": MAX_OUTPUT_TOKENS,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingLevel": THINKING_LEVEL, "includeThoughts": False},
                "responseJsonSchema": {
                    "type": "object",
                    "required": ["choices"],
                    "additionalProperties": False,
                    "properties": {
                        "choices": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": len(options),
                            "items": {"type": "integer", "minimum": 1, "maximum": len(options)},
                        },
                    },
                },
            },
        }
    )
    if len(body) > MAX_INPUT_BYTES:
        raise _ProviderError(_Code.UNAUTHORIZED_INPUT)
    return body


def _selection_text(raw: bytes, attempt: _Attempt) -> str:
    try:
        _, root = decode_response(raw)
    except ResponseDecodeError:
        raise _ProviderError(_Code.INVALID_ENVELOPE) from None
    if not isinstance(root, dict) or root.keys() - {
        "candidates",
        "promptFeedback",
        "usageMetadata",
        "modelVersion",
        "responseId",
        "modelStatus",
    }:
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    usage = root.get("usageMetadata", {})
    if not isinstance(usage, dict):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    for field_name in (
        "promptTokenCount",
        "candidatesTokenCount",
        "thoughtsTokenCount",
        "totalTokenCount",
        "cachedContentTokenCount",
    ):
        if field_name in usage:
            value = usage[field_name]
            if type(value) is not int or not 0 <= value <= 2_000_000:
                raise _ProviderError(_Code.INVALID_ENVELOPE)
            attempt.tokens[field_name] = value
    if attempt.tokens.get("cachedContentTokenCount", 0):
        raise _ProviderError(_Code.CACHE_USE_REPORTED)
    if "modelVersion" in root:
        version = root["modelVersion"]
        if not isinstance(version, str) or not re.fullmatch(
            re.escape(MODEL) + r"(?:-[a-z0-9-]{1,32})?", version
        ):
            raise _ProviderError(_Code.INVALID_ENVELOPE)
        attempt.model_version = version
    feedback = root.get("promptFeedback", {})
    if not isinstance(feedback, dict):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    if feedback.get("blockReason", "BLOCK_REASON_UNSPECIFIED") != "BLOCK_REASON_UNSPECIFIED":
        raise _ProviderError(_Code.BLOCKED)
    candidates = root.get("candidates")
    if (
        not isinstance(candidates, list)
        or len(candidates) != 1
        or not isinstance(candidates[0], dict)
    ):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    candidate = candidates[0]
    index = candidate.get("index", 0)
    if (
        type(index) is not int
        or index != 0
        or candidate.keys()
        - {
            "index",
            "content",
            "finishReason",
            "finishMessage",
            "safetyRatings",
            "citationMetadata",
            "tokenCount",
            "avgLogprobs",
            "logprobsResult",
        }
    ):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    finish = candidate.get("finishReason")
    if finish == "MAX_TOKENS":
        raise _ProviderError(_Code.TRUNCATED)
    if finish in ("SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"):
        raise _ProviderError(_Code.BLOCKED)
    if finish != "STOP":
        raise _ProviderError(_Code.UNEXPECTED_FINISH)
    content = candidate.get("content")
    if (
        not isinstance(content, dict)
        or content.keys() != {"role", "parts"}
        or content["role"] != "model"
    ):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    parts = content["parts"]
    if not isinstance(parts, list) or len(parts) != 1 or not isinstance(parts[0], dict):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    part = parts[0]
    text = part.get("text")
    if (
        part.keys() - {"text", "thought", "thoughtSignature"}
        or part.get("thought", False) is not False
        or ("thoughtSignature" in part and not isinstance(part["thoughtSignature"], str))
        or not isinstance(text, str)
        or not text.strip()
    ):
        raise _ProviderError(_Code.INVALID_ENVELOPE)
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError:
        raise _ProviderError(_Code.INVALID_ENVELOPE) from None
    if size > MAX_SELECTION_BYTES:
        raise _ProviderError(_Code.RESPONSE_TOO_LARGE)
    return text


class _CaseProvider:
    """One scoped provider for one case loaded from the checksum-pinned fixture."""

    def __init__(
        self,
        case: PilotCase,
        permit: object,
        budget: _PilotBudget,
        client: httpx.AsyncClient,
        gate: asyncio.Semaphore,
        read_key: Callable[[], str],
    ) -> None:
        self._case = case
        self._permit = permit
        self._budget = budget
        self._client = client
        self._gate = gate
        self._read_key = read_key
        self._calls = 0

    async def generate(self, request: GenerationRequest) -> str:
        correction = self._calls == 1
        if (
            _ACTIVE_CASE.get() is not self._permit
            or not self._case.offers
            or request.language != self._case.language
            or request.choices != self._case.choices()
            or self._calls >= 2
            or request.correction != (MALFORMED_SELECTION_CORRECTION if correction else None)
            or request.deadline is None
            or not math.isfinite(request.deadline)
        ):
            raise _ProviderError(_Code.UNAUTHORIZED_INPUT)
        loop = asyncio.get_running_loop()
        if request.deadline <= loop.time():
            raise TimeoutError("timeout")
        if request.deadline - loop.time() > 30:
            raise _ProviderError(_Code.UNAUTHORIZED_INPUT)
        self._calls += 1
        try:
            async with asyncio.timeout_at(request.deadline), self._gate:
                return await self._post(correction, request.deadline)
        except httpx.TimeoutException:
            raise TimeoutError("timeout") from None

    async def _post(self, correction: bool, deadline: float) -> str:
        if _ACTIVE_CASE.get() is not self._permit or not self._case.offers:
            raise _ProviderError(_Code.UNAUTHORIZED_INPUT)
        body = _payload(self._case, correction)
        if self._budget.stop is not None:
            raise _ProviderError(self._budget.stop)
        if len(self._budget.attempts) >= self._budget.limit:
            self._budget.stop = _Code.BUDGET_EXHAUSTED
            raise _ProviderError(self._budget.stop)
        try:
            key = developer_api_key(self._read_key)
        except ValueError:
            self._budget.stop = _Code.AUTHENTICATION
            raise _ProviderError(_Code.AUTHENTICATION) from None
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("timeout")
        attempt = self._budget.reserve(self._case.id, correction)
        started = perf_counter()
        try:
            async with self._client.stream(
                "POST",
                _ENDPOINT,
                content=body,
                headers={
                    "x-goog-api-key": key,
                    "Accept-Encoding": "identity",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(
                    connect=min(2, remaining),
                    read=min(4, remaining),
                    write=min(2, remaining),
                    pool=min(1, remaining),
                ),
            ) as response:
                attempt.http_status = response.status_code
                if response.status_code in (401, 403):
                    self._budget.stop = _Code.AUTHENTICATION
                    raise _ProviderError(_Code.AUTHENTICATION)
                if response.status_code == 429:
                    self._budget.stop = _Code.QUOTA
                    raise _ProviderError(_Code.QUOTA)
                if response.status_code != 200:
                    raise _ProviderError(_Code.HTTP_ERROR)
                if (
                    response.headers.get("content-encoding", "identity").lower() != "identity"
                    or response.headers.get("content-type", "").split(";", 1)[0].lower()
                    != "application/json"
                ):
                    raise _ProviderError(_Code.INVALID_ENVELOPE)
                data = bytearray()
                async for part in response.aiter_bytes():
                    if len(data) + len(part) > MAX_RESPONSE_BYTES:
                        raise _ProviderError(_Code.RESPONSE_TOO_LARGE)
                    data.extend(part)
                text = _selection_text(bytes(data), attempt)
                attempt.outcome = _Code.OK
                return text
        except _ProviderError as exc:
            attempt.outcome = exc.code
            if exc.code == _Code.CACHE_USE_REPORTED:
                self._budget.stop = exc.code
            raise
        except httpx.TimeoutException:
            attempt.outcome = _Code.TIMEOUT
            raise TimeoutError("timeout") from None
        except (httpx.HTTPError, OSError):
            attempt.outcome = _Code.TRANSPORT_ERROR
            raise _ProviderError(_Code.TRANSPORT_ERROR) from None
        except asyncio.CancelledError:
            attempt.outcome = (
                _Code.TIMEOUT if asyncio.get_running_loop().time() >= deadline else _Code.CANCELLED
            )
            raise
        finally:
            attempt.latency_ms = round((perf_counter() - started) * 1000, 3)


async def run_hosted_pilot(
    approval: HostedAuthorization,
    read_key: Callable[[], str],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    """Run only repository fixtures. No entry point accepts caller evidence or prompts."""
    fixture = approval.load()
    budget = _PilotBudget(approval.max_http_attempts)
    rows = []
    skipped = []
    gate = asyncio.Semaphore(1)
    transport = (
        transport
        if transport is not None
        else httpx.AsyncHTTPTransport(
            retries=0,
            trust_env=False,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )
    )
    async with httpx.AsyncClient(
        transport=transport,
        trust_env=False,
        follow_redirects=False,
    ) as client:
        for case in fixture.cases:
            if budget.stop or (case.offers and len(budget.attempts) >= budget.limit):
                skipped.append(case.id)
                continue
            permit = object()
            provider = _CaseProvider(case, permit, budget, client, gate, read_key)
            started = perf_counter()
            token = _ACTIVE_CASE.set(permit)
            try:
                result = await run_case(fixture, case, provider)
            finally:
                _ACTIVE_CASE.reset(token)
            rows.append(describe_case(case, result, (perf_counter() - started) * 1000))
    return {
        "fixture_version": fixture.version,
        "fixture_sha256": FIXTURE_SHA256,
        "provider": "google-gemini-developer",
        "model": MODEL,
        "thinking_level": THINKING_LEVEL,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "free_tier_confirmed_by_operator": True,
        "http_attempt_limit": budget.limit,
        "http_attempts": len(budget.attempts),
        "http_cases_attempted": len({attempt.case_id for attempt in budget.attempts}),
        "http_corrections": sum(attempt.correction for attempt in budget.attempts),
        "status": (
            "incomplete"
            if skipped or budget.stop
            else "complete"
            if all(row["matches_label"] for row in rows)
            else "complete_with_failures"
        ),
        "estimated_cost_usd": 0,
        "stop_reason": budget.stop or (_Code.BUDGET_EXHAUSTED if skipped else None),
        "skipped_cases": skipped,
        "attempts": [asdict(attempt) for attempt in budget.attempts],
        "summary": summarize(rows, sum(bool(case.offers) for case in fixture.cases)),
    }
