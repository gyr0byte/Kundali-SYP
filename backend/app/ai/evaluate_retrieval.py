"""Offline retrieval evaluation and explicitly gated Vertex pilot entry point."""

import argparse
import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter_ns

import httpx
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.embeddings import EmbeddingError, EmbeddingQuery, Vector
from app.ai.gemini_embeddings import MAX_ATTEMPTS, AttemptOutcome, VertexGeminiEmbeddings
from app.ai.retrieval import TIER2_BONUS
from app.ai.retrieval_evaluation import (
    Dataset,
    PreparedCase,
    evaluate,
    keyword_comparisons,
    load_dataset,
    prepare,
    semantic_fixture_rank,
)
from app.knowledge.provenance import sha256
from app.knowledge.retrieval import Match, Search


class PilotRejected(ValueError):
    """Script-supplied, sanitized diagnostic."""


@dataclass(frozen=True)
class PilotSettings:
    authorized: bool
    approved_digest: str
    project: str
    location: str
    max_attempts: int
    max_spend_microusd: int
    price_per_1000_microusd: int


@dataclass(frozen=True)
class WorkItem:
    id: str
    content: str
    query: EmbeddingQuery | None = None


def _work(dataset: Dataset, cases: tuple[PreparedCase, ...]) -> tuple[WorkItem, ...]:
    documents = tuple(
        WorkItem(passage.id, passage.text)
        for passage in dataset.passages
        if passage.state == "approved"
    )
    queries = {}
    for case in cases:
        intent = case.resolution.intent
        if (
            intent is not None
            and intent.targets == (case.case.target,)
            and case.resolution.scope == case.case.scope
        ):
            canonical = intent.encode()
            queries[canonical] = WorkItem(sha256(canonical.encode("utf-8")), canonical, intent)
    return documents + tuple(queries[key] for key in sorted(queries))


def _units(byte_count: int) -> int:
    return (byte_count + 999) // 1000


def _plan(work: tuple[WorkItem, ...]) -> dict[str, int]:
    queries = sum(item.query is not None for item in work)
    return {
        "documents": len(work) - queries,
        "unique_canonical_queries": queries,
        "maximum_attempts": MAX_ATTEMPTS * len(work),
        "maximum_charge_units": MAX_ATTEMPTS
        * sum(_units(len(item.content.encode("utf-8"))) for item in work),
    }


@dataclass
class Usage:
    settings: PilotSettings
    attempts: int = 0
    estimated_microusd: int = 0
    usage_reports: int = 0
    reported_tokens: int = 0

    def attempt(self, byte_count: int) -> None:
        cost = _units(byte_count) * self.settings.price_per_1000_microusd
        if self.attempts >= self.settings.max_attempts:
            raise PilotRejected("Hosted request budget exhausted")
        if self.estimated_microusd + cost > self.settings.max_spend_microusd:
            raise PilotRejected("Hosted spending estimate exhausted")
        self.attempts += 1
        self.estimated_microusd += cost

    def report(self, tokens: int | None) -> None:
        if tokens is not None:
            self.usage_reports += 1
            self.reported_tokens += tokens


def hosted_report(
    settings: PilotSettings,
    access_token: Callable[[], str],
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, object], bool]:
    if not settings.authorized:
        raise PilotRejected("Hosted execution requires explicit authorization")
    dataset, digest = load_dataset()
    if digest != settings.approved_digest:
        raise PilotRejected("Approved evaluation dataset checksum does not match")
    if (
        min(settings.max_attempts, settings.max_spend_microusd, settings.price_per_1000_microusd)
        < 1
    ):
        raise PilotRejected("Hosted attempt, spending and price limits must be positive")
    cases = prepare(dataset)
    work = _work(dataset, cases)
    plan = _plan(work)
    if (
        plan["maximum_attempts"] > settings.max_attempts
        or plan["maximum_charge_units"] * settings.price_per_1000_microusd
        > settings.max_spend_microusd
    ):
        raise PilotRejected("Hosted budgets do not cover the bounded retry plan")

    usage = Usage(settings)
    attempts_log: list[dict[str, object]] = []

    def record_attempt(outcome: AttemptOutcome, elapsed_ms: float) -> None:
        attempts_log.append({"outcome": outcome, "latency_ms": round(elapsed_ms, 4)})

    provider = VertexGeminiEmbeddings(
        settings.project,
        settings.location,
        access_token,
        transport=transport,
        on_attempt=usage.attempt,
        on_attempt_result=record_attempt,
        on_usage=usage.report,
    )
    requests: list[dict[str, object]] = []
    queries: dict[str, Vector] = {}
    documents: dict[str, Vector] = {}
    for item in work:
        started = perf_counter_ns()
        attempts, reports, tokens, estimated_cost = (
            usage.attempts,
            usage.usage_reports,
            usage.reported_tokens,
            usage.estimated_microusd,
        )
        failed = False
        try:
            if item.query is None:
                documents[item.id] = provider.embed_document(item.content)
            else:
                queries[item.content] = provider.embed_query(item.query)
        except EmbeddingError:
            failed = True
        requests.append(
            {
                "id": item.id,
                "kind": "query" if item.query is not None else "document",
                "attempts": usage.attempts - attempts,
                "attempt_details": attempts_log[attempts:],
                "failed": failed,
                "latency_ms": round((perf_counter_ns() - started) / 1_000_000, 4),
                "reported_tokens": usage.reported_tokens - tokens
                if usage.usage_reports > reports
                else None,
                "estimated_microusd": usage.estimated_microusd - estimated_cost,
            }
        )
        if failed:
            # Partial vectors would change the ranking pool. Preserve telemetry, withhold scores.
            break

    def compare(bonus: float) -> dict[str, object]:
        def rank(session: Session, search: Search, prepared: PreparedCase) -> tuple[Match, ...]:
            assert prepared.resolution.intent is not None
            vector = queries.get(prepared.resolution.intent.encode())
            if vector is None:
                return ()
            return semantic_fixture_rank(session, search, vector, documents, tier2_bonus=bonus)

        return evaluate(dataset, cases, rank)

    successes = len(queries) + len(documents)
    complete = successes == len(work)
    return {
        "dataset_version": dataset.version,
        "dataset_sha256": digest,
        "provider": provider.config.model_dump(mode="json"),
        "vertex_project_sha256": sha256(settings.project.encode("utf-8")),
        "status": "complete" if complete else "incomplete",
        "budget": {
            "max_attempts": settings.max_attempts,
            "max_spend_microusd": settings.max_spend_microusd,
            "price_per_1000_microusd": settings.price_per_1000_microusd,
            "plan": plan,
        },
        "usage": {
            **{key: value for key, value in asdict(usage).items() if key != "settings"},
            "failed_attempts": sum(attempt["outcome"] != "ok" for attempt in attempts_log),
        },
        "requests": requests,
        "keyword": keyword_comparisons(dataset, cases),
        "semantic": {"no_tier_bonus": compare(0), "tier2_bonus_0_01": compare(TIER2_BONUS)}
        if complete
        else None,
    }, complete


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorize-hosted", action="store_true")
    parser.add_argument("--approved-dataset-sha256", default="")
    parser.add_argument("--project", default="")
    parser.add_argument("--location", default="")
    parser.add_argument("--max-attempts", type=int, default=0)
    parser.add_argument("--max-spend-microusd", type=int, default=0)
    parser.add_argument("--price-per-1000-microusd", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.output:
            args.output = args.output.resolve()
            if args.output.drive.upper() != "D:":
                raise PilotRejected("Evaluation export path must be on D:")
            if args.output.exists() or not args.output.parent.is_dir():
                raise PilotRejected(
                    "Evaluation export requires a new file in an existing directory"
                )
        complete = True
        if args.authorize_hosted:
            report, complete = hosted_report(
                PilotSettings(
                    args.authorize_hosted,
                    args.approved_dataset_sha256,
                    args.project,
                    args.location,
                    args.max_attempts,
                    args.max_spend_microusd,
                    args.price_per_1000_microusd,
                ),
                lambda: os.environ.get("KUNDALI_VERTEX_ACCESS_TOKEN", ""),
            )
        else:
            dataset, digest = load_dataset()
            cases = prepare(dataset)
            report = {
                "dataset_version": dataset.version,
                "dataset_sha256": digest,
                "hosted_plan": _plan(_work(dataset, cases)),
                "keyword": keyword_comparisons(dataset, cases),
            }
        result = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(result)
        else:
            print(result, end="")
        return 0 if complete else 1
    except PilotRejected as exc:
        parser.exit(2, f"{exc}\n")
    except (OSError, ValidationError, ValueError):
        parser.exit(2, "Invalid evaluation input or unavailable export path\n")


if __name__ == "__main__":
    raise SystemExit(main())
