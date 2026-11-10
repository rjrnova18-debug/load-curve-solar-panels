"""Solar PV system sizing with the peak-sun-hours method.

``size_systems`` is the only public entry point. It sizes the three System types
for the same Load analysis so they can be compared side by side:

* on-grid:  the array covers a share of the annual consumption; the grid serves
  night-time and peaks, so there are no batteries and the inverter follows the array.
* hybrid:   the array covers all consumption over the year; batteries store
  the night-time energy of the highest-consumption month.
* off-grid: the array covers the critical month (highest consumption relative to
  sun); batteries hold a full day of the highest-consumption month per day of autonomy.
  Not feasible (``None``) when a month with consumption has no sun at all.

Night-time energy passes through the battery, so hybrid and off-grid arrays also
produce what the battery loses: daytime + night-time / battery efficiency.

Every number comes from evaluating a Calculation step (see ``calculation``), and
the steps travel with the result, so the formulas shown to the user are exactly
the ones that produced the numbers.
"""

import math

from pydantic import BaseModel, ConfigDict

from loadcurve.domain.analysis import LoadAnalysis, MonthlyEnergy
from loadcurve.domain.calculation import (
    CalculationStep,
    Expression,
    ceiling,
    constant,
    evaluate,
    over,
    plus,
    step,
    times,
    value,
)
from loadcurve.domain.models import (
    DAYS_IN_MONTH,
    SizingAssumptions,
    SolarResource,
    SystemType,
)

W_PER_KW = 1000.0
DAYS_IN_YEAR = sum(DAYS_IN_MONTH)


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
    steps: tuple[CalculationStep, ...]  # how each number above was calculated


class SizingComparison(BaseModel):
    """The three System types sized for the same site."""

    model_config = ConfigDict(frozen=True)

    on_grid: SystemSizing
    hybrid: SystemSizing
    off_grid: SystemSizing | None  # None: some month with consumption has no sun


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
    energy = times(
        value("coverage", assumptions.on_grid_coverage),
        value("daily_energy", analysis.annual_energy_kwh / DAYS_IN_YEAR, "kWh"),
    )
    sun = value("peak_sun_hours", _yearly_peak_sun_hours(solar), "h", "year")
    array = _array_step(energy, sun, assumptions)
    panels = _panels_step(array.result, assumptions)
    inverter = step(
        "inverter_power",
        over(
            times(
                value("panel_count", panels.result),
                value("panel_power", assumptions.panel_power_w, "W"),
            ),
            constant(W_PER_KW),
        ),
        "kW",
    )
    return _system(
        SystemType.ON_GRID, None, energy, sun, array, panels, None, inverter, assumptions
    )


def _size_hybrid(
    analysis: LoadAnalysis, solar: SolarResource, assumptions: SizingAssumptions
) -> SystemSizing:
    energy = _energy_through_battery(
        analysis.annual_daytime_energy_kwh / DAYS_IN_YEAR,
        analysis.annual_nighttime_energy_kwh / DAYS_IN_YEAR,
        assumptions,
    )
    sun = value("peak_sun_hours", _yearly_peak_sun_hours(solar), "h", "year")
    array = _array_step(energy, sun, assumptions)
    panels = _panels_step(array.result, assumptions)
    busiest_night_kwh = max(month.nighttime_energy_kwh / month.days for month in analysis.monthly)
    battery = _battery_step(value("nighttime_energy", busiest_night_kwh, "kWh", "max"), assumptions)
    inverter = _load_inverter_step(analysis, assumptions)
    return _system(
        SystemType.HYBRID, None, energy, sun, array, panels, battery, inverter, assumptions
    )


def _size_off_grid(
    analysis: LoadAnalysis, solar: SolarResource, assumptions: SizingAssumptions
) -> SystemSizing | None:
    def required_kwp(month: MonthlyEnergy) -> float:
        daily_kwh = _energy_to_produce_kwh(month, assumptions) / month.days
        psh = solar.peak_sun_hours[month.month - 1]
        if psh == 0:
            return math.inf if daily_kwh > 0 else 0.0
        return daily_kwh / (psh * assumptions.performance_ratio)

    # max() keeps the first month on ties. Rounding first stops float noise (monthly
    # energy divided back by its days differs by ~1e-15) from breaking a real tie.
    critical = max(analysis.monthly, key=lambda month: round(required_kwp(month), 9))
    if math.isinf(required_kwp(critical)):
        return None

    in_month = f"month:{critical.month}"
    energy = _energy_through_battery(
        critical.daytime_energy_kwh / critical.days,
        critical.nighttime_energy_kwh / critical.days,
        assumptions,
        qualifier=in_month,
    )
    sun = value("peak_sun_hours", solar.peak_sun_hours[critical.month - 1], "h", in_month)
    array = _array_step(energy, sun, assumptions)
    panels = _panels_step(array.result, assumptions)
    busiest_day_kwh = max(month.energy_kwh / month.days for month in analysis.monthly)
    battery = _battery_step(
        times(
            value("daily_energy", busiest_day_kwh, "kWh", "max"),
            value("days_of_autonomy", assumptions.days_of_autonomy),
        ),
        assumptions,
    )
    inverter = _load_inverter_step(analysis, assumptions)
    return _system(
        SystemType.OFF_GRID,
        critical.month,
        energy,
        sun,
        array,
        panels,
        battery,
        inverter,
        assumptions,
    )


# ---------- Formulas ----------


def _energy_through_battery(
    daytime_kwh: float,
    nighttime_kwh: float,
    assumptions: SizingAssumptions,
    qualifier: str | None = None,
) -> Expression:
    """Daily energy the array must produce when night-time runs from the battery."""
    return plus(
        value("daytime_energy", daytime_kwh, "kWh", qualifier),
        over(
            value("nighttime_energy", nighttime_kwh, "kWh", qualifier),
            value("battery_efficiency", assumptions.battery_efficiency),
        ),
    )


def _array_step(
    energy: Expression, sun: Expression, assumptions: SizingAssumptions
) -> CalculationStep:
    """Array power = daily energy / (peak sun hours x performance ratio)."""
    return step(
        "array_power",
        over(energy, times(sun, value("performance_ratio", assumptions.performance_ratio))),
        "kWp",
    )


def _panels_step(array_kwp: float, assumptions: SizingAssumptions) -> CalculationStep:
    """Whole panels: array power x 1000 / panel power, rounded up."""
    return step(
        "panel_count",
        ceiling(
            over(
                times(value("array_power", array_kwp, "kWp"), constant(W_PER_KW)),
                value("panel_power", assumptions.panel_power_w, "W"),
            )
        ),
        "",
    )


def _battery_step(energy_to_store: Expression, assumptions: SizingAssumptions) -> CalculationStep:
    """Nominal capacity whose usable, after-losses share holds the energy."""
    return step(
        "battery_capacity",
        over(
            energy_to_store,
            times(
                value("depth_of_discharge", assumptions.battery_depth_of_discharge),
                value("battery_efficiency", assumptions.battery_efficiency),
            ),
        ),
        "kWh",
    )


def _load_inverter_step(analysis: LoadAnalysis, assumptions: SizingAssumptions) -> CalculationStep:
    """Inverter that serves the highest hourly peak of the year with a safety margin."""
    highest_multiplier = max(month.seasonal_multiplier for month in analysis.monthly)
    return step(
        "inverter_power",
        times(
            value("peak_power", analysis.whole_day.peak_power_w / W_PER_KW, "kW"),
            value("seasonal_multiplier", highest_multiplier, "", "max"),
            value("inverter_safety_factor", assumptions.inverter_safety_factor),
        ),
        "kW",
    )


# ---------- Helpers ----------


def _system(
    system_type: SystemType,
    design_month: int | None,
    energy: Expression,
    sun: Expression,
    array: CalculationStep,
    panels: CalculationStep,
    battery: CalculationStep | None,
    inverter: CalculationStep,
    assumptions: SizingAssumptions,
) -> SystemSizing:
    steps = tuple(s for s in (array, panels, battery, inverter) if s is not None)
    panel_count = int(panels.result)
    return SystemSizing(
        system_type=system_type,
        design_month=design_month,
        design_daily_energy_kwh=evaluate(energy),
        design_peak_sun_hours=evaluate(sun),
        array_power_kwp=array.result,
        panel_count=panel_count,
        installed_power_kwp=panel_count * assumptions.panel_power_w / W_PER_KW,
        battery_capacity_kwh=battery.result if battery else 0.0,
        inverter_power_kw=inverter.result,
        steps=steps,
    )


def _energy_to_produce_kwh(month: MonthlyEnergy, assumptions: SizingAssumptions) -> float:
    """Energy the array must produce in a month when night-time runs from the battery."""
    return month.daytime_energy_kwh + month.nighttime_energy_kwh / assumptions.battery_efficiency


def _yearly_peak_sun_hours(solar: SolarResource) -> float:
    """Peak sun hours averaged over the days of the year."""
    yearly_sun_hours = sum(
        psh * days for psh, days in zip(solar.peak_sun_hours, DAYS_IN_MONTH, strict=True)
    )
    return yearly_sun_hours / DAYS_IN_YEAR
