import pytest

from loadcurve.domain.analysis import analyze
from loadcurve.domain.models import AnalysisSettings, DaytimeWindow, Load, LoadTable


def hours_on(*hours: int) -> list[int]:
    return [1 if hour in hours else 0 for hour in range(24)]


def table(*loads: Load) -> LoadTable:
    return LoadTable(loads=loads)


# The sample Load table shipped with the legacy Streamlit app.
LEGACY_TEMPLATE = table(
    Load(name="Server rack", rated_power_w=1500, schedule=hours_on(*range(8, 19))),
    Load(name="Kitchen fridge", rated_power_w=350, schedule=[1] * 24),
    Load(name="Projector", rated_power_w=300, schedule=hours_on(9, 10, 11, 15, 16, 17)),
    Load(name="AC office", rated_power_w=3514, schedule=hours_on(9, 10, 13, 14, 23)),
    Load(name="AC principal", rated_power_w=3514, schedule=hours_on(10, 11, 20, 21, 22, 23)),
    Load(
        name="AC coordination",
        rated_power_w=3514.4,
        schedule=hours_on(5, 6, 7, 8, 9, 10, 13, 14, 15, 16, 22, 23),
    ),
    Load(name="Water pump", rated_power_w=1491.6, schedule=hours_on(6, 8, 11, 20, 21, 22, 23)),
    Load(
        name="Refrigerator",
        rated_power_w=1000,
        schedule=hours_on(0, 1, 2, 3, 4, 5, 6, 12, 13, 14, 15, 16, 21, 22),
    ),
    Load(name="Fans", rated_power_w=5400, schedule=hours_on(0, 1, 2, 3, 4, 11, 13, 15, 17, 22)),
    Load(name="LED lighting", rated_power_w=1200, schedule=hours_on(4, 5, 6, 10, 12, 14, 16, 21)),
)


class TestHourlyProfile:
    def test_usage_factor_scales_the_rated_power(self) -> None:
        fridge = Load(name="Fridge", rated_power_w=350, usage_factor=0.4, schedule=[1] * 24)

        result = analyze(table(fridge))

        assert result.hourly_profile_w == pytest.approx([140.0] * 24)
        assert result.whole_day.energy_kwh == pytest.approx(3.36)

    def test_adds_up_every_load_running_in_each_hour(self) -> None:
        result = analyze(LEGACY_TEMPLATE)

        # Hour 0: kitchen fridge + refrigerator + fans.
        assert result.hourly_profile_w[0] == pytest.approx(350 + 1000 + 5400)
        # Hour 12: server rack + kitchen fridge + refrigerator + LED lighting.
        assert result.hourly_profile_w[12] == pytest.approx(1500 + 350 + 1000 + 1200)

    def test_keeps_each_load_hourly_power_in_table_order(self) -> None:
        result = analyze(LEGACY_TEMPLATE)

        assert [load.name for load in result.loads] == [load.name for load in LEGACY_TEMPLATE.loads]
        column_sums = [sum(load.hourly_power_w[h] for load in result.loads) for h in range(24)]
        assert column_sums == pytest.approx(result.hourly_profile_w)


class TestLoadDurationCurve:
    def test_is_the_profile_sorted_from_highest_to_lowest(self) -> None:
        result = analyze(LEGACY_TEMPLATE)

        assert list(result.load_duration_curve_w) == sorted(result.hourly_profile_w, reverse=True)


class TestPeriodStats:
    def test_night_peak_reports_the_hour_of_the_maximum(self) -> None:
        # The legacy app used idxmin() here and reported the hour of the minimum.
        result = analyze(
            table(
                Load(name="Heater", rated_power_w=500, schedule=hours_on(20)),
                Load(name="Router", rated_power_w=100, schedule=hours_on(2)),
            )
        )

        assert result.nighttime.peak_power_w == pytest.approx(500)
        assert result.nighttime.peak_hour == 20

    def test_ties_resolve_to_the_first_hour_of_the_period(self) -> None:
        result = analyze(
            table(Load(name="Lights", rated_power_w=100, schedule=hours_on(*range(18, 23))))
        )

        assert result.nighttime.peak_hour == 18
        assert result.nighttime.base_hour == 23

    def test_splits_energy_between_day_and_night(self) -> None:
        result = analyze(
            table(
                Load(name="Heater", rated_power_w=2000, schedule=hours_on(7)),
                Load(name="Lights", rated_power_w=100, schedule=hours_on(*range(18, 23))),
            )
        )

        assert result.daytime.energy_kwh == pytest.approx(2.0)
        assert result.nighttime.energy_kwh == pytest.approx(0.5)
        assert result.whole_day.energy_kwh == pytest.approx(2.5)
        assert (result.daytime.hours, result.nighttime.hours) == (12, 12)

    def test_daytime_window_can_cross_midnight(self) -> None:
        settings = AnalysisSettings(daytime_window=DaytimeWindow(start_hour=22, end_hour=6))
        night_shift = Load(name="Night shift", rated_power_w=1000, schedule=hours_on(23, 0, 1))

        result = analyze(table(night_shift), settings)

        assert result.daytime_hours == (22, 23, 0, 1, 2, 3, 4, 5)
        assert result.daytime.energy_kwh == pytest.approx(3.0)
        assert result.nighttime.energy_kwh == pytest.approx(0.0)

    def test_load_factor_is_mean_over_peak(self) -> None:
        result = analyze(
            table(Load(name="Pump", rated_power_w=1000, schedule=hours_on(*range(12))))
        )

        assert result.whole_day.load_factor == pytest.approx(0.5)

    def test_load_factor_is_zero_when_nothing_runs(self) -> None:
        result = analyze(table(Load(name="Pump", rated_power_w=1000, schedule=hours_on(10))))

        assert result.nighttime.peak_power_w == 0
        assert result.nighttime.load_factor == 0


class TestYearProjection:
    def test_without_seasonal_change_a_year_is_365_typical_days(self) -> None:
        result = analyze(LEGACY_TEMPLATE)

        assert result.annual_energy_kwh == pytest.approx(result.whole_day.energy_kwh * 365)

    def test_seasonal_multiplier_scales_only_its_month(self) -> None:
        fridge = Load(name="Fridge", rated_power_w=1000, schedule=[1] * 24)  # 24 kWh/day
        settings = AnalysisSettings(seasonal_multipliers=[1.5] + [1.0] * 11)

        result = analyze(table(fridge), settings)

        january, february = result.monthly[0], result.monthly[1]
        assert january.energy_kwh == pytest.approx(24 * 31 * 1.5)
        assert february.energy_kwh == pytest.approx(24 * 28)
        assert result.annual_energy_kwh == pytest.approx(24 * 365 + 24 * 31 * 0.5)

    def test_monthly_day_and_night_add_up_to_the_total(self) -> None:
        result = analyze(LEGACY_TEMPLATE)

        for month in result.monthly:
            assert month.daytime_energy_kwh + month.nighttime_energy_kwh == pytest.approx(
                month.energy_kwh
            )
        assert [month.month for month in result.monthly] == list(range(1, 13))
