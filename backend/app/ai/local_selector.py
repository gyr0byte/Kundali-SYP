"""Deterministic selection over the request's already eligible choices."""

import json
from dataclasses import dataclass

from app.ai.llm_adapter import GenerationAbstained, GenerationRequest
from app.ai.schemas import ClaimKind
from app.knowledge.chunking import Applicability
from app.knowledge.retrieval import Match, matches_target


@dataclass(frozen=True, slots=True, repr=False)
class LocalSelector:
    target: Applicability | None
    candidates: tuple[Match, ...] = ()

    async def generate(self, request: GenerationRequest) -> str:
        target = self.target
        if target is None or any(choice.target != target for choice in request.choices):
            raise GenerationAbstained
        if not self.candidates:
            (choice,) = request.choices if len(request.choices) == 1 else (None,)
            expected = "dasha_fact" if target.topic == "dasha" else "chart_fact"
            if choice is None or choice.number != 1 or choice.kind != expected:
                raise GenerationAbstained
            return '{"choices":[1]}'

        if len(request.choices) != len(self.candidates):
            raise GenerationAbstained
        ranked = []
        for rank, (choice, candidate) in enumerate(
            zip(request.choices, self.candidates, strict=True), 1
        ):
            expected_kind: ClaimKind
            if target.topic in {"planet_general", "sign_general", "house_general"}:
                expected_kind = "general_explanation"
            else:
                expected_kind = (
                    "conditional_interpretation" if candidate.conditional else "interpretation"
                )
            if (
                choice.number != rank
                or choice.kind != expected_kind
                or not matches_target(candidate.applicability, target)
            ):
                raise GenerationAbstained
            # Within a language and rule specificity, keep the canonical keyword ranking.
            ranked.append(
                (
                    candidate.language != request.language,
                    candidate.applicability != target,
                    rank,
                    choice.number,
                )
            )
        return json.dumps({"choices": [min(ranked)[-1]]})
