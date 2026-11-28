"""Version 1 generated claim selections. No model-authored prose is accepted."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BeforeValidator, Field, StringConstraints, field_validator

from app.api.schemas.dasha import DashaQuery
from app.knowledge.chunking import (
    DashaRule,
    HouseGeneral,
    NakshatraRule,
    PadaRule,
    PlanetGeneral,
    PlanetInHouse,
    PlanetInSign,
    SignGeneral,
)
from app.knowledge.provenance import Record

Locale = Literal["en", "ne"]
ClaimCertainty = Literal["exact", "approximate"]
Reference = Annotated[
    str, StringConstraints(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9_:+.-]+$")
]
CitationReference = Annotated[
    str,
    StringConstraints(
        max_length=200,
        pattern=r"^[a-z0-9][a-z0-9-]{0,79}@[1-9][0-9]{0,9}/[a-z0-9][a-z0-9-]{0,79}@[1-9][0-9]{0,9}$",
    ),
]
GeneralTarget = Annotated[PlanetGeneral | SignGeneral | HouseGeneral, Field(discriminator="topic")]
PlacementTarget = Annotated[
    PlanetInHouse | PlanetInSign | NakshatraRule | PadaRule, Field(discriminator="topic")
]


def _check_evaluation_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Expected an explicit-offset ISO timestamp")
    DashaQuery(as_of=value)
    return datetime.fromisoformat(value)


class PlacementClaim(Record):
    kind: Literal["chart_fact"]
    fact_id: Reference
    target: PlacementTarget
    certainty: ClaimCertainty


class ActiveDashaClaim(Record):
    kind: Literal["dasha_fact"]
    fact_id: Reference
    target: DashaRule
    period_id: Reference
    evaluated_at: Annotated[AwareDatetime, BeforeValidator(_check_evaluation_timestamp)]
    certainty: ClaimCertainty


FactClaim = Annotated[PlacementClaim | ActiveDashaClaim, Field(discriminator="kind")]


class GeneralExplanation(Record):
    kind: Literal["general_explanation"]
    target: GeneralTarget
    citation_id: CitationReference


class Interpretation(Record):
    kind: Literal["interpretation", "conditional_interpretation"]
    basis: FactClaim
    citation_id: CitationReference


class Abstention(Record):
    kind: Literal["abstention"]
    reason: Literal["ambiguous_request", "unsupported_request", "insufficient_evidence"]


Claim = Annotated[
    PlacementClaim | ActiveDashaClaim | GeneralExplanation | Interpretation | Abstention,
    Field(discriminator="kind"),
]


class Reading(Record):
    schema_version: Literal[1]
    language: Locale
    snapshot_id: UUID | None = None
    claims: tuple[Claim, ...] = Field(min_length=1, max_length=12)

    @field_validator("schema_version", mode="before")
    @classmethod
    def version_must_be_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Expected integer schema version")
        return value
