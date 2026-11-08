"""Solar PV system sizing with the peak-sun-hours method.

``size_systems`` is the only public entry point. It sizes the three System types
for the same Load analysis so they can be compared side by side:

* on-grid:  the array covers a share of the annual consumption; the grid serves
  night-time and peaks, so there are no batteries and the inverter follows the array.
* hybrid:   the array covers all consumption over the year; batteries store
  the night-time energy of the highest-consumption month.
* off-grid: the array covers the critical month (highest consumption relative to
  sun); batteries hold a full day of the highest-consumption month per day of autonomy.

Night-time energy passes through the battery, so hybrid and off-grid arrays also
produce what the battery loses: daytime + night-time / battery efficiency.
"""

import math

from pydantic import BaseModel, ConfigDict

from loadcurve.domain.analysis import LoadAnalysis, MonthlyEnergy
from loadcurve.domain.models import (
    DAYS_IN_MONTH,
    SizingAssumptions,
    SolarResource,
    SystemType,
)

W_PER_KW = 1000.0


class SystemSizing(BaseModel):
    """The sized equipment for one System type, plus the design basis behind it."""

    model_config = ConfigDict(frozen=True)

    system_type: SystemType
    design_month: int | None  # 1 = January; None when sized on the yearly average
    design_daily_energy_kwh: float  # energy the array must deliver per day
    design_peak_sun_hours: float
    array_power_kwp: float  # required power, before rounding up to whole panels
    panel_count: int
    installed_power_kwp: float
    battery_capacity_kwh: float  # nominal capacity; 0 for on-grid
    inverter_power_kw: float


class SizingComparison(BaseModel):
    """The three System types sized for the same site."""

    model_config = ConfigDict(frozen=True)

    on_grid: SystemSizing
    hybrid: SystemSizing
    off_grid: SystemSizing


def size_systems(
    analysis: LoadAnalysis,
    solar_resource: SolarResource,
    assumptions: SizingAssumptions,
) -> SizingComparison:
    """Size an on-grid, a hybrid and an off-grid system for the analysed Load table."""
    return SizingComparison(
        on_grid=_size_on_grid(analysis, solar_resource, assumptions),
        hybrid=_size_hybrid(analysis, solar_resource, assumptions),
        off_grid=_size_off_grid(analysis, solar_resource, assumptions),
    )


def _size_on_grid(
    analysis: LoadAnalysis, solar: SolarResource, assumptions: SizingAssumptions
) -> SystemSizing:
    yearly_target_kwh = analysis.annual_energy_kwh * assumptions.on_grid_coverage
    array_kwp, daily_kwh, psh = _yearly_array(yearly_target_kwh, solar, assumptions)
    panel_count, installed_kwp = _panels(array_kwp, assumptions)

    return SystemSizing(
        system_type=SystemType.ON_GRID,
        design_month=None,
        design_daily_energy_kwh=daily_kwh,
        design_peak_sun_hours=psh,
        array_power_kwp=array_kwp,
        panel_count=panel_count,
        installed_power_kwp=installed_kwp,
        battery_capacity_kwh=0.0,
        inverter_power_kw=installed_kwp,
    )


def _size_hybrid(
    analysis: LoadAnalysis, solar: SolarResource, assumptions: SizingAssumptions
) -> SystemSizing:
    yearly_target_kwh = sum(
        _energy_to_produce_kwh(month, assumptions) for month in analysis.monthly
    )
    array_kwp, daily_kwh, psh = _yearly_array(yearly_target_kwh, solar, assumptions)
    panel_count, installed_kwp = _panels(array_kwp, assumptions)
    night_kwh = max(month.nighttime_energy_kwh / month.days for month in analysis.monthly)

    return SystemSizing(
        system_type=SystemType.HYBRID,
        design_month=None,
        design_daily_energy_kwh=daily_kwh,
        design_peak_sun_hours=psh,
        array_power_kwp=array_kwp,
        panel_count=panel_count,
        installed_power_kwp=installed_kwp,
        battery_capacity_kwh=_battery_capacity_kwh(night_kwh, assumptions),
        inverter_power_kw=_load_inverter_kw(analysis, assumptions),
    )


def _size_off_grid(
    analysis: LoadAnalysis, solar: SolarResource, assumptions: SizingAssumptions
) -> SystemSizing:
    def required_kwp(month: MonthlyEnergy) -> float:
        daily_kwh = _energy_to_produce_kwh(month, assumptions) / month.days
        psh = solar.peak_sun_hours[month.month - 1]
        return daily_kwh / (psh * assumptions.performance_ratio)

    # max() keeps the first month on ties, so the result is deterministic.
    critical = max(analysis.monthly, key=required_kwp)
    array_kwp = required_kwp(critical)
    panel_count, installed_kwp = _panels(array_kwp, assumptions)
    busiest_day_kwh = max(month.energy_kwh / month.days for month in analysis.monthly)

    return SystemSizing(
        system_type=SystemType.OFF_GRID,
        design_month=critical.month,
        design_daily_energy_kwh=_energy_to_produce_kwh(critical, assumptions) / critical.days,
        design_peak_sun_hours=solar.peak_sun_hours[critical.month - 1],
        array_power_kwp=array_kwp,
        panel_count=panel_count,
        installed_power_kwp=installed_kwp,
        battery_capacity_kwh=_battery_capacity_kwh(
            busiest_day_kwh * assumptions.days_of_autonomy, assumptions
        ),
        inverter_power_kw=_load_inverter_kw(analysis, assumptions),
    )


def _energy_to_produce_kwh(month: MonthlyEnergy, assumptions: SizingAssumptions) -> float:
    """Energy the array must produce in a month when night-time runs from the battery."""
    return month.daytime_energy_kwh + month.nighttime_energy_kwh / assumptions.battery_efficiency


def _yearly_array(
    yearly_target_kwh: float, solar: SolarResource, assumptions: SizingAssumptions
) -> tuple[float, float, float]:
    """Array power that produces the yearly target, with its daily equivalents.

    Returns (array kWp, design daily energy in kWh, day-weighted average peak sun hours).
    """
    days_in_year = sum(DAYS_IN_MONTH)
    yearly_sun_hours = sum(
        psh * days for psh, days in zip(solar.peak_sun_hours, DAYS_IN_MONTH, strict=True)
    )
    array_kwp = yearly_target_kwh / (yearly_sun_hours * assumptions.performance_ratio)
    return array_kwp, yearly_target_kwh / days_in_year, yearly_sun_hours / days_in_year


def _panels(array_kwp: float, assumptions: SizingAssumptions) -> tuple[int, float]:
    """Whole number of panels covering the array, and the power they actually install."""
    # Rounding first stops float noise (16.0000000001) from adding a phantom panel.
    exact_count = round(array_kwp * W_PER_KW / assumptions.panel_power_w, 6)
    panel_count = math.ceil(exact_count)
    return panel_count, panel_count * assumptions.panel_power_w / W_PER_KW


def _battery_capacity_kwh(energy_to_store_kwh: float, assumptions: SizingAssumptions) -> float:
    """Nominal capacity whose usable, after-losses share holds the given energy."""
    usable_share = assumptions.battery_depth_of_discharge * assumptions.battery_efficiency
    return energy_to_store_kwh / usable_share


def _load_inverter_kw(analysis: LoadAnalysis, assumptions: SizingAssumptions) -> float:
    """Inverter that serves the highest hourly peak of the year with a safety margin."""
    highest_multiplier = max(month.seasonal_multiplier for month in analysis.monthly)
    peak_w = analysis.whole_day.peak_power_w * highest_multiplier
    return peak_w * assumptions.inverter_safety_factor / W_PER_KW
