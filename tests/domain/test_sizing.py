"""Expected values are worked out by hand from a 1 kW load running 24 h a day.

With the default 06-18 daytime window: 12 kWh by day + 12 kWh by night = 24 kWh/day.
Through a 0.95-efficient battery the array must produce 12 + 12 / 0.95 = 24.6316 kWh/day.
"""

import pytest
from pydantic import ValidationError

from loadcurve.domain.analysis import analyze
from loadcurve.domain.models import (
    AnalysisSettings,
    Load,
    LoadTable,
    SizingAssumptions,
    SolarResource,
    SystemType,
)
from loadcurve.domain.sizing import size_systems

CONSTANT_1KW = LoadTable(loads=[Load(name="Base load", rated_power_w=1000, schedule=[1] * 24)])
SUNNY = SolarResource(peak_sun_hours=[5.0] * 12)
ASSUMPTIONS = SizingAssumptions(panel_power_w=500)  # everything else at its default
DAILY_TO_PRODUCE = 12 + 12 / 0.95


def size(settings: AnalysisSettings | None = None, **assumption_overrides):
    assumptions = SizingAssumptions(**({"panel_power_w": 500} | assumption_overrides))
    return size_systems(analyze(CONSTANT_1KW, settings or AnalysisSettings()), SUNNY, assumptions)


class TestOnGrid:
    def test_array_covers_the_yearly_consumption(self) -> None:
        on_grid = size().on_grid

        # 24 kWh/day / (5 h x 0.75) = 6.4 kWp -> 12.8 panels of 500 W -> 13 panels.
        assert on_grid.system_type is SystemType.ON_GRID
        assert on_grid.array_power_kwp == pytest.approx(6.4)
        assert on_grid.panel_count == 13
        assert on_grid.installed_power_kwp == pytest.approx(6.5)
        assert on_grid.design_daily_energy_kwh == pytest.approx(24)
        assert on_grid.design_peak_sun_hours == pytest.approx(5)

    def test_has_no_batteries_and_the_inverter_follows_the_array(self) -> None:
        on_grid = size().on_grid

        assert on_grid.battery_capacity_kwh == 0
        assert on_grid.inverter_power_kw == pytest.approx(on_grid.installed_power_kwp)

    def test_coverage_scales_the_array(self) -> None:
        assert size(on_grid_coverage=0.5).on_grid.array_power_kwp == pytest.approx(3.2)

    def test_an_exact_fit_does_not_add_a_panel(self) -> None:
        # 6.4 kWp / 400 W = exactly 16 panels.
        assert size(panel_power_w=400).on_grid.panel_count == 16


class TestHybrid:
    def test_array_also_covers_battery_losses(self) -> None:
        hybrid = size().hybrid

        assert hybrid.array_power_kwp == pytest.approx(DAILY_TO_PRODUCE / (5 * 0.75))
        assert hybrid.design_month is None

    def test_battery_stores_the_night(self) -> None:
        # 12 kWh / (0.8 DoD x 0.95 efficiency)
        assert size().hybrid.battery_capacity_kwh == pytest.approx(12 / 0.76)

    def test_inverter_serves_the_peak_with_margin(self) -> None:
        assert size().hybrid.inverter_power_kw == pytest.approx(1.0 * 1.25)


class TestOffGrid:
    def test_battery_holds_full_days_of_autonomy(self) -> None:
        assert size().off_grid.battery_capacity_kwh == pytest.approx(24 / 0.76)
        assert size(days_of_autonomy=2).off_grid.battery_capacity_kwh == pytest.approx(48 / 0.76)

    def test_designs_for_the_critical_month_not_just_the_darkest(self) -> None:
        # January uses 50% more energy with 5 h of sun; June is darker (4 h) but uses less.
        # January needs 1.5 x 24.63 / 5 = 7.39 kWh per sun hour, June 24.63 / 4 = 6.16.
        settings = AnalysisSettings(seasonal_multipliers=[1.5] + [1.0] * 11)
        solar = SolarResource(peak_sun_hours=[5, 5, 5, 5, 5, 4, 5, 5, 5, 5, 5, 5])

        off_grid = size_systems(analyze(CONSTANT_1KW, settings), solar, ASSUMPTIONS).off_grid

        assert off_grid.design_month == 1
        assert off_grid.design_peak_sun_hours == pytest.approx(5)
        assert off_grid.array_power_kwp == pytest.approx(1.5 * DAILY_TO_PRODUCE / (5 * 0.75))

    def test_with_flat_consumption_the_darkest_month_decides(self) -> None:
        solar = SolarResource(peak_sun_hours=[5, 5, 5, 5, 5, 4, 5, 5, 5, 5, 5, 5])

        off_grid = size_systems(analyze(CONSTANT_1KW), solar, ASSUMPTIONS).off_grid

        assert off_grid.design_month == 6
        assert off_grid.array_power_kwp == pytest.approx(DAILY_TO_PRODUCE / (4 * 0.75))

    def test_inverter_covers_the_highest_seasonal_peak(self) -> None:
        settings = AnalysisSettings(seasonal_multipliers=[1.5] + [1.0] * 11)

        assert size(settings).off_grid.inverter_power_kw == pytest.approx(1.5 * 1.25)


class TestMonthsWithoutSun:
    # Tromso, Norway (69.6 N), as returned by PVGIS: no sun in December.
    POLAR = SolarResource(
        peak_sun_hours=[0.02, 0.97, 2.96, 4.71, 5.1, 4.45, 4.31, 3.66, 2.56, 1.27, 0.12, 0.0]
    )

    def test_off_grid_is_not_feasible(self) -> None:
        comparison = size_systems(analyze(CONSTANT_1KW), self.POLAR, ASSUMPTIONS)

        assert comparison.off_grid is None

    def test_grid_connected_systems_still_size_on_the_yearly_average(self) -> None:
        comparison = size_systems(analyze(CONSTANT_1KW), self.POLAR, ASSUMPTIONS)

        yearly_psh = comparison.on_grid.design_peak_sun_hours
        assert 0 < yearly_psh < 5
        assert comparison.on_grid.array_power_kwp == pytest.approx(24 / (yearly_psh * 0.75))
        assert comparison.hybrid.battery_capacity_kwh > 0

    def test_off_grid_ignores_dark_months_without_consumption(self) -> None:
        settings = AnalysisSettings(seasonal_multipliers=[1.0] * 11 + [0.0])  # empty in December

        comparison = size_systems(analyze(CONSTANT_1KW, settings), self.POLAR, ASSUMPTIONS)

        assert comparison.off_grid is not None
        assert comparison.off_grid.design_month == 1  # 0.02 sun hours in January


class TestInputValidation:
    @pytest.mark.parametrize("bad_month", [-1.0, 13.0])
    def test_solar_resource_rejects_impossible_sun_hours(self, bad_month: float) -> None:
        with pytest.raises(ValidationError):
            SolarResource(peak_sun_hours=[bad_month] + [5.0] * 11)

    def test_solar_resource_rejects_a_year_without_sun(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            SolarResource(peak_sun_hours=[0.0] * 12)

        assert excinfo.value.errors()[0]["type"] == "no_solar_resource"

    def test_solar_resource_needs_twelve_months(self) -> None:
        with pytest.raises(ValidationError):
            SolarResource(peak_sun_hours=[5.0] * 11)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"performance_ratio": 1.2},
            {"battery_depth_of_discharge": 0},
            {"inverter_safety_factor": 0.9},
            {"on_grid_coverage": 1.5},
        ],
    )
    def test_assumptions_reject_out_of_range_values(self, overrides: dict) -> None:
        with pytest.raises(ValidationError):
            SizingAssumptions(**overrides)
