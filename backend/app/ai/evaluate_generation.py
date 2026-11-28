"""Offline baseline and explicitly authorized synthetic Gemini pilot CLI."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from time import perf_counter

from pydantic import ValidationError

from app.ai.gemini_developer_generation import HostedAuthorization, run_hosted_pilot
from app.ai.generation_pilot_fixture import (
    FIXTURE_SHA256,
    PilotRejected,
    describe_case,
    load_fixture,
    run_case,
    summarize,
)
from app.ai.llm_adapter import GenerationRequest


class _FirstChoice:
    async def generate(self, request: GenerationRequest) -> str:
        return json.dumps({"choices": [request.choices[0].number]})


async def offline_baseline() -> dict[str, object]:
    fixture = load_fixture()
    rows = []
    for case in fixture.cases:
        start = perf_counter()
        result = await run_case(fixture, case, _FirstChoice())
        rows.append(describe_case(case, result, (perf_counter() - start) * 1000))
    return {
        "fixture_version": fixture.version,
        "fixture_sha256": FIXTURE_SHA256,
        "provider": "local-first-choice",
        "http_attempts": 0,
        "summary": summarize(rows, sum(bool(case.offers) for case in fixture.cases)),
    }


def _output_path(value: Path | None) -> Path | None:
    if value is None:
        return None
    path = value.resolve()
    if path.drive.upper() != "D:" or path.exists() or not path.parent.is_dir():
        raise PilotRejected("Use a new output file in an existing directory on D:")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-hosted", action="store_true")
    parser.add_argument("--confirm-free-tier", action="store_true")
    parser.add_argument("--approved-fixture-sha256", default="")
    parser.add_argument("--max-http-attempts", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        path = _output_path(args.output)
        hosted = None
        if args.authorize_hosted:
            if path is None:
                raise PilotRejected("Hosted evaluation requires an output file on D:")
            hosted = asyncio.run(
                run_hosted_pilot(
                    HostedAuthorization(
                        args.authorize_hosted,
                        args.confirm_free_tier,
                        args.approved_fixture_sha256,
                        args.max_http_attempts,
                    ),
                    lambda: os.environ.get("KUNDALI_GEMINI_API_KEY", ""),
                )
            )
        elif args.confirm_free_tier or args.approved_fixture_sha256 or args.max_http_attempts:
            raise PilotRejected("Hosted settings require explicit authorization")
        report = {"baseline": asyncio.run(offline_baseline()), "hosted": hosted}
        text = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
        if path is None:
            print(text, end="")
        else:
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        return int(hosted is not None and hosted["status"] != "complete")
    except PilotRejected as exc:
        parser.exit(2, f"{exc}\n")
    except (OSError, ValidationError, ValueError):
        parser.exit(2, "Invalid pilot configuration or unavailable export path\n")


if __name__ == "__main__":
    raise SystemExit(main())
