"""Vimshottari timing, natal-fact compatibility, and published examples."""

from datetime import UTC, date, datetime, time, timedelta, timezone
from fractions import Fraction
from typing import cast

import pytest

from app.calc.dasha import (
    BirthTimeCertainty,
    DashaInputError,
    DashaLevel,
    DashaLord,
    DashaPeriod,
    calculate_vimshottari,
    calculate_vimshottari_from_chart,
    dasha_lord_of_nakshatra,
)
from app.calc.facts import ChartFactPlacement, ChartFacts, ChartSettings, compute_chart_facts
from app.calc.timeconv import TimeInput

BIRTH = datetime(2000, 4, 28, 9, 50, tzinfo=UTC)
ONE_MICROSECOND = timedelta(microseconds=1)
LORDS = ("Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury")
LORD_YEARS = dict(zip(LORDS, (7, 20, 6, 10, 7, 18, 16, 19, 17), strict=True))


@pytest.mark.parametrize("index", range(27))
def test_nakshatra_lord_mapping(index: int) -> None:
    assert dasha_lord_of_nakshatra(index) == LORDS[index % 9]


@pytest.mark.parametrize("index", [-1, 27, True, 0.0])
def test_invalid_nakshatra_indices(index: int) -> None:
    with pytest.raises(DashaInputError, match="Nakshatra index"):
        dasha_lord_of_nakshatra(index)


@pytest.mark.parametrize("index", range(9))
def test_original_mahadasha_order_for_every_opening_lord(index: int) -> None:
    timeline = calculate_vimshottari(
        (index + 0.5) * 360 / 27, BIRTH, year_days=360, time_certainty="exact"
    )
    assert tuple(md.lord for md in timeline.mahadashas) == LORDS[index:] + LORDS[:index]
    assert timeline.mahadashas[0].start_utc < BIRTH


@pytest.mark.parametrize("longitude", range(0, 360, 40))
def test_exact_nakshatra_boundaries_start_new_mahadashas(longitude: int) -> None:
    timeline = calculate_vimshottari(longitude, BIRTH, year_days=360, time_certainty="exact")
    initial = timeline.initial_balance
    assert initial.nakshatra_index == longitude * 27 // 360
    assert initial.elapsed_fraction == 0
    assert initial.remaining_years == LORD_YEARS[initial.lord]
    assert timeline.mahadashas[0].start_utc == BIRTH
    active = timeline.active_at(BIRTH)
    assert active is not None
    assert active.mahadasha.lord == active.antardasha.lord == active.pratyantardasha.lord


def test_longitude_quantization_matches_the_natal_side_of_boundaries() -> None:
    before = calculate_vimshottari(13.333333, BIRTH, year_days=360, time_certainty="exact")
    after = calculate_vimshottari(13.333334, BIRTH, year_days=360, time_certainty="exact")
    near_end = calculate_vimshottari(39.999999, BIRTH, year_days=360, time_certainty="exact")
    assert before.initial_balance.lord == DashaLord.KETU
    assert after.initial_balance.lord == DashaLord.VENUS
    assert near_end.initial_balance.lord == DashaLord.SUN
    assert near_end.initial_balance.remaining_years == Fraction(9, 20_000_000)
    assert near_end.mahadashas[0].end_utc_exclusive - BIRTH == timedelta(seconds=13.9968)
    zero = calculate_vimshottari(0, BIRTH, year_days=360, time_certainty="exact")
    assert calculate_vimshottari(360, BIRTH, year_days=360, time_certainty="exact") == zero
    assert calculate_vimshottari(359.9999996, BIRTH, year_days=360, time_certainty="exact") == zero


def _assert_partition(
    parent: DashaPeriod, level: DashaLevel, exact_parent_microseconds: Fraction
) -> None:
    first = LORDS.index(parent.lord)
    children = parent.children
    assert tuple(child.lord for child in children) == LORDS[first:] + LORDS[:first]
    boundary = parent.start_utc
    for child in children:
        assert child.level == level
        assert child.start_utc == boundary
        assert child.start_utc < child.end_utc_exclusive
        duration = (child.end_utc_exclusive - child.start_utc) // ONE_MICROSECOND
        expected_duration = exact_parent_microseconds * LORD_YEARS[child.lord] / 120
        assert abs(duration - expected_duration) <= 1
        boundary = child.end_utc_exclusive
    assert boundary == parent.end_utc_exclusive


@pytest.mark.parametrize("year_days", [360.0, 365.2425, 365.25])
def test_cycle_and_every_nested_period_partition(year_days: float) -> None:
    timeline = calculate_vimshottari(302.383333, BIRTH, year_days=year_days, time_certainty="exact")
    mds = timeline.mahadashas
    year_microseconds = Fraction(str(year_days)) * 86_400_000_000
    boundary = mds[0].start_utc
    seen_ids = set()
    for md in mds:
        assert md.level == "MD"
        assert md.start_utc == boundary
        boundary = md.end_utc_exclusive
        duration = year_microseconds * LORD_YEARS[md.lord]
        assert (md.end_utc_exclusive - md.start_utc) // ONE_MICROSECOND == duration
        _assert_partition(md, "AD", duration)
        seen_ids.add(md.period_id)
        for ad in md.children:
            ad_duration = duration * LORD_YEARS[ad.lord] / 120
            _assert_partition(ad, "PD", ad_duration)
            seen_ids.add(ad.period_id)
            for pd in ad.children:
                assert pd.children == ()
                seen_ids.add(pd.period_id)
    assert len(seen_ids) == 9 + 81 + 729
    assert (boundary - mds[0].start_utc) // ONE_MICROSECOND == 120 * year_microseconds


def test_rao_example_50_initial_balance_and_actual_periods_at_birth() -> None:
    # The published example uses Moon at 2°23′ Aquarius and a 360-day year.
    local_birth = datetime(2000, 4, 28, 5, 50, tzinfo=timezone(timedelta(hours=-4)))
    timeline = calculate_vimshottari(
        302 + 23 / 60, local_birth, year_days=360, time_certainty="exact"
    )
    assert timeline.birth_utc == BIRTH
    assert timeline.moon_longitude == 302.383333
    assert timeline.initial_balance.nakshatra == "Dhanishta"
    assert timeline.initial_balance.remaining_years == Fraction("2.248750175")
    active = timeline.active_at(BIRTH)
    assert active is not None
    assert (active.mahadasha.lord, active.antardasha.lord, active.pratyantardasha.lord) == (
        "Mars",
        "Ketu",
        "Jupiter",
    )
    # The published balance is 809.55 days. Canonical lunar rounding accounts for +5.4432 s.
    published_end = BIRTH + timedelta(days=809, seconds=47_520)
    assert active.mahadasha.end_utc_exclusive - published_end == timedelta(seconds=5.4432)


def test_rao_venus_subperiod_examples_use_full_parent_duration() -> None:
    timeline = calculate_vimshottari(20.0, BIRTH, year_days=360, time_certainty="exact")
    venus = timeline.mahadashas[0]
    venus_ad, sun_ad, *_ = venus.children
    venus_pd = venus_ad.children[0]
    assert timeline.initial_balance.elapsed_fraction == Fraction(1, 2)
    assert timeline.initial_balance.remaining_years == 10
    assert venus.start_utc == BIRTH - timedelta(days=3600)
    assert venus_ad.lord == venus_pd.lord == DashaLord.VENUS
    assert venus_ad.end_utc_exclusive - venus_ad.start_utc == timedelta(days=1200)
    assert sun_ad.lord == DashaLord.SUN
    assert sun_ad.end_utc_exclusive - sun_ad.start_utc == timedelta(days=360)
    assert venus_pd.end_utc_exclusive - venus_pd.start_utc == timedelta(days=200)


def test_lookup_uses_half_open_boundaries_at_each_level_and_at_cycle_end() -> None:
    timeline = calculate_vimshottari(20, BIRTH, year_days=365.25, time_certainty="exact")
    md, next_md, *_ = timeline.mahadashas
    ad, next_ad, *_ = md.children
    pd, next_pd, *_ = ad.children
    for left, right in [(md, next_md), (ad, next_ad), (pd, next_pd)]:
        before = timeline.active_at(right.start_utc - ONE_MICROSECOND)
        at = timeline.active_at(right.start_utc)
        assert before is not None and at is not None
        assert left in (before.mahadasha, before.antardasha, before.pratyantardasha)
        assert right in (at.mahadasha, at.antardasha, at.pratyantardasha)
    assert timeline.active_at(md.start_utc - ONE_MICROSECOND) is None
    assert timeline.active_at(md.start_utc) is not None
    assert timeline.active_at(timeline.mahadashas[-1].end_utc_exclusive) is None


def test_deterministic_ids_and_presentation_clip_leave_full_boundaries_intact() -> None:
    timeline = calculate_vimshottari(20, BIRTH, year_days=360, time_certainty="exact")
    offset = BIRTH.astimezone(timezone(timedelta(hours=5, minutes=45)))
    assert calculate_vimshottari(20.0, offset, year_days=360.0, time_certainty="exact") == timeline
    assert (
        calculate_vimshottari(20, BIRTH, year_days=365.25, time_certainty="exact").timeline_id
        != timeline.timeline_id
    )
    assert (
        calculate_vimshottari(20.000001, BIRTH, year_days=360, time_certainty="exact").timeline_id
        != timeline.timeline_id
    )
    md = timeline.mahadashas[0]
    end = md.end_utc_exclusive
    visible = md.clip(BIRTH, end + timedelta(days=1))
    assert visible is not None
    assert visible.period is md
    assert visible.period.start_utc < visible.start_utc == BIRTH
    assert visible.end_utc_exclusive == end
    assert md.clip(end, end + ONE_MICROSECOND) is None
    with pytest.raises(DashaInputError, match="display interval"):
        md.clip(BIRTH, BIRTH)
    with pytest.raises(DashaInputError, match="aware datetime"):
        timeline.active_at(BIRTH.replace(tzinfo=None))


@pytest.mark.parametrize("longitude", [-1, 360.001, float("nan"), float("inf"), True, "20"])
def test_invalid_moon_longitude(longitude: float) -> None:
    with pytest.raises(DashaInputError, match="Moon longitude"):
        calculate_vimshottari(longitude, BIRTH, year_days=360, time_certainty="exact")


@pytest.mark.parametrize("year_days", [365.0, 365.2422, float("inf"), "360", None, True])
def test_unsupported_year_conventions(year_days: float) -> None:
    with pytest.raises(DashaInputError, match="year length"):
        calculate_vimshottari(20, BIRTH, year_days=year_days, time_certainty="exact")


def test_invalid_birth_instants() -> None:
    with pytest.raises(DashaInputError, match="aware datetime"):
        calculate_vimshottari(20, BIRTH.replace(tzinfo=None), year_days=360, time_certainty="exact")
    with pytest.raises(DashaInputError, match="cycle falls outside"):
        calculate_vimshottari(
            0, datetime.max.replace(tzinfo=UTC), year_days=360, time_certainty="exact"
        )
    with pytest.raises(DashaInputError, match="cycle falls outside"):
        calculate_vimshottari(
            20, datetime.min.replace(tzinfo=UTC), year_days=360, time_certainty="exact"
        )


def test_birth_time_certainty_is_enforced() -> None:
    approximate = calculate_vimshottari(20, BIRTH, year_days=360, time_certainty="approximate")
    exact = calculate_vimshottari(20, BIRTH, year_days=360, time_certainty="exact")
    assert approximate.is_conditional
    assert approximate.time_certainty == "approximate"
    assert not exact.is_conditional
    assert approximate.initial_balance == exact.initial_balance
    assert approximate.timeline_id != exact.timeline_id
    for certainty in ("unknown", "estimated"):
        with pytest.raises(DashaInputError, match="requires an exact or approximate birth time"):
            calculate_vimshottari(
                20, BIRTH, year_days=360, time_certainty=cast(BirthTimeCertainty, certainty)
            )


@pytest.fixture
def natal_chart() -> ChartFacts:
    return compute_chart_facts(
        TimeInput(
            date=date(2015, 5, 15),
            time=time(12, 17),
            latitude=51.5074,
            longitude=-0.1278,
            timezone="Europe/London",
        ),
        ChartSettings(year_days=365.2425),
    )


def test_chart_adapter_uses_persisted_moon_and_chart_settings(natal_chart: ChartFacts) -> None:
    moon = next(
        f for f in natal_chart.facts if isinstance(f, ChartFactPlacement) and f.id == "f_moon"
    )
    timeline = calculate_vimshottari_from_chart(natal_chart, time_certainty="approximate")
    assert timeline.initial_balance.nakshatra == moon.nakshatra
    assert timeline.is_conditional
    assert timeline == calculate_vimshottari(
        moon.longitude,
        datetime(2015, 5, 15, 11, 17, tzinfo=UTC),
        year_days=365.2425,
        time_certainty="approximate",
    )
    with pytest.raises(DashaInputError, match="requires an exact or approximate birth time"):
        calculate_vimshottari_from_chart(natal_chart, time_certainty="unknown")
    with pytest.raises(DashaInputError, match="requires natal chart facts"):
        calculate_vimshottari_from_chart(cast(ChartFacts, {"moon": {}}), time_certainty="exact")


def test_chart_adapter_rejects_inconsistent_or_missing_moon(natal_chart: ChartFacts) -> None:
    moon = next(
        f for f in natal_chart.facts if isinstance(f, ChartFactPlacement) and f.id == "f_moon"
    )
    for invalid_facts in ([], [moon, moon], [moon.model_copy(update={"planet": "Sun"})]):
        with pytest.raises(DashaInputError, match="one Moon placement"):
            calculate_vimshottari_from_chart(
                natal_chart.model_copy(update={"facts": invalid_facts}), time_certainty="exact"
            )
    for patch in (
        {"nakshatra": "Invalid"},
        {"pada": 0},
        {"longitude": moon.longitude + 0.0000001},
    ):
        with pytest.raises(DashaInputError, match="inconsistent"):
            calculate_vimshottari_from_chart(
                natal_chart.model_copy(update={"facts": [moon.model_copy(update=patch)]}),
                time_certainty="exact",
            )
    invalid_metadata = natal_chart.metadata.model_copy(update={"datetime_utc_iso": "invalid"})
    with pytest.raises(DashaInputError, match="recorded UTC instant"):
        calculate_vimshottari_from_chart(
            natal_chart.model_copy(update={"metadata": invalid_metadata}), time_certainty="exact"
        )
