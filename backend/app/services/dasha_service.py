"""Derive Vimshottari responses from a previously authorized natal snapshot."""

from datetime import datetime
from fractions import Fraction

from app.api.schemas.chart import ChartSnapshotResponse
from app.api.schemas.dasha import (
    ActiveDashaPeriods,
    DashaActivePeriodFact,
    DashaBalance,
    DashaBalanceFact,
    DashaFact,
    DashaFactSource,
    DashaLookup,
    DashaPeriodBoundary,
    DashaPeriodResponse,
    DashaRatio,
    DashaResponse,
)
from app.calc.dasha import DASHA_METHOD, DashaPeriod, calculate_vimshottari_from_chart
from app.db.models.profile import TimeCertainty


def _ratio(value: Fraction) -> DashaRatio:
    return DashaRatio(numerator=value.numerator, denominator=value.denominator)


def _boundary(period: DashaPeriod) -> DashaPeriodBoundary:
    return DashaPeriodBoundary(
        period_id=period.period_id,
        level=period.level,
        lord=period.lord,
        start_utc=period.start_utc,
        end_utc_exclusive=period.end_utc_exclusive,
    )


def _period_tree(period: DashaPeriod) -> DashaPeriodResponse:
    return DashaPeriodResponse(
        **_boundary(period).model_dump(),
        children=[_period_tree(child) for child in period.children],
    )


def derive_snapshot_dasha(
    snapshot: ChartSnapshotResponse,
    as_of: datetime | None,
) -> DashaResponse:
    timeline = calculate_vimshottari_from_chart(
        snapshot.chart,
        time_certainty="exact" if snapshot.time_certainty == TimeCertainty.EXACT else "approximate",
    )
    source = DashaFactSource(
        snapshot_id=snapshot.snapshot_id,
        timeline_id=timeline.timeline_id,
        method=DASHA_METHOD,
        time_certainty=timeline.time_certainty,
        is_conditional=timeline.is_conditional,
    )
    scope = f"{source.snapshot_id}:{source.method}:{source.timeline_id}"
    initial = timeline.initial_balance
    balance = DashaBalance(
        lord=initial.lord,
        nakshatra_index=initial.nakshatra_index,
        nakshatra=initial.nakshatra,
        elapsed_fraction=_ratio(initial.elapsed_fraction),
        remaining_years=_ratio(initial.remaining_years),
    )
    facts: list[DashaFact] = [
        DashaBalanceFact(**source.model_dump(), fact_id=f"{scope}:balance", balance=balance),
    ]
    if as_of is None:
        lookup = DashaLookup(as_of=None, status="not_requested")
    elif as_of < timeline.birth_utc:
        lookup = DashaLookup(as_of=as_of, status="before_birth")
    elif (active := timeline.active_at(as_of)) is None:
        lookup = DashaLookup(as_of=as_of, status="outside_cycle")
    else:
        periods = ActiveDashaPeriods(
            mahadasha=_boundary(active.mahadasha),
            antardasha=_boundary(active.antardasha),
            pratyantardasha=_boundary(active.pratyantardasha),
        )
        lookup = DashaLookup(as_of=as_of, status="active", periods=periods)
        for period in (periods.mahadasha, periods.antardasha, periods.pratyantardasha):
            facts.append(
                DashaActivePeriodFact(
                    **source.model_dump(),
                    fact_id=f"{scope}:{period.level}:{as_of.isoformat(timespec='microseconds')}",
                    evaluated_at=as_of,
                    period=period,
                )
            )
    return DashaResponse(
        **source.model_dump(),
        chart_id=snapshot.chart.chart_id,
        year_days=timeline.year_days,
        profile_revision=snapshot.profile_revision,
        is_current_profile_revision=snapshot.is_current_profile_revision,
        birth_utc=timeline.birth_utc,
        start_utc=timeline.mahadashas[0].start_utc,
        end_utc_exclusive=timeline.mahadashas[-1].end_utc_exclusive,
        initial_balance=balance,
        mahadashas=[_period_tree(period) for period in timeline.mahadashas],
        lookup=lookup,
        facts=facts,
    )
