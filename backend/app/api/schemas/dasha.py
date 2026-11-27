"""Snapshot-scoped Vimshottari schedules and grounding facts."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, PlainSerializer

from app.calc.dasha import DashaLevel, DashaLord, RecordedTimeCertainty

UtcTimestamp = Annotated[
    datetime,
    PlainSerializer(lambda value: value.astimezone(UTC).isoformat(timespec="microseconds"), str),
]
DashaMethod = Literal["vimshottari-v1"]


class DashaQuery(BaseModel):
    model_config = {"extra": "forbid"}

    as_of: str | None = Field(
        default=None,
        pattern=(
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(\.[0-9]{1,6})?(Z|[+-]([01][0-9]|2[0-3]):[0-5][0-9])$"
        ),
        description="ISO 8601 instant with an explicit UTC offset and up to six fractional digits",
    )


class DashaRatio(BaseModel):
    numerator: int
    denominator: int


class DashaBalance(BaseModel):
    lord: DashaLord
    nakshatra_index: int
    nakshatra: str
    elapsed_fraction: DashaRatio
    remaining_years: DashaRatio


class DashaPeriodBoundary(BaseModel):
    period_id: str
    level: DashaLevel
    lord: DashaLord
    start_utc: UtcTimestamp
    end_utc_exclusive: UtcTimestamp


class DashaPeriodResponse(DashaPeriodBoundary):
    children: list["DashaPeriodResponse"]


class ActiveDashaPeriods(BaseModel):
    mahadasha: DashaPeriodBoundary
    antardasha: DashaPeriodBoundary
    pratyantardasha: DashaPeriodBoundary


class DashaLookup(BaseModel):
    as_of: UtcTimestamp | None
    status: Literal["not_requested", "before_birth", "outside_cycle", "active"]
    periods: ActiveDashaPeriods | None = None


class DashaFactSource(BaseModel):
    snapshot_id: UUID
    timeline_id: str
    method: DashaMethod
    time_certainty: RecordedTimeCertainty
    is_conditional: bool


class DashaBalanceFact(DashaFactSource):
    fact_type: Literal["initial_balance"] = "initial_balance"
    fact_id: str
    balance: DashaBalance


class DashaActivePeriodFact(DashaFactSource):
    fact_type: Literal["active_period"] = "active_period"
    fact_id: str
    evaluated_at: UtcTimestamp
    period: DashaPeriodBoundary


DashaFact = Annotated[DashaBalanceFact | DashaActivePeriodFact, Field(discriminator="fact_type")]


class DashaResponse(DashaFactSource):
    chart_id: str
    year_days: float
    profile_revision: int
    is_current_profile_revision: bool
    birth_utc: UtcTimestamp
    start_utc: UtcTimestamp
    end_utc_exclusive: UtcTimestamp
    initial_balance: DashaBalance
    mahadashas: list[DashaPeriodResponse]
    lookup: DashaLookup
    facts: list[DashaFact]


class DashaEligibilityError(BaseModel):
    code: Literal["DASHA_UNKNOWN_BIRTH_TIME"]
    detail: str
