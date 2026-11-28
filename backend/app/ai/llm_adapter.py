"""Async provider boundary for selecting from vetted structured claims."""

from dataclasses import dataclass
from typing import Literal, Protocol

from app.ai.schemas import ClaimKind, Locale
from app.knowledge.chunking import Applicability


@dataclass(frozen=True, slots=True)
class ClaimChoice:
    number: int
    kind: ClaimKind
    target: Applicability


@dataclass(frozen=True, slots=True)
class Correction:
    code: Literal["malformed_selection"]
    guidance: Literal["Return a JSON object with a choices array of distinct offered integers."]


MALFORMED_SELECTION_CORRECTION = Correction(
    "malformed_selection",
    "Return a JSON object with a choices array of distinct offered integers.",
)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Contains only local choice numbers and allowlisted concepts."""

    language: Locale
    choices: tuple[ClaimChoice, ...]
    correction: Correction | None = None
    deadline: float | None = None


class GenerationProvider(Protocol):
    async def generate(self, request: GenerationRequest) -> str | bytes:
        """Return JSON with a choices array. Cooperate with asyncio cancellation."""
        ...


class GenerationAbstained(RuntimeError):
    """The selector has no defensible choice from the provided options."""
