"""Load analysis: from a Load table to its daily profile and yearly projection.

``analyze`` is the only public entry point. Every hourly value is the average
power over that hour, so a value in W is also the energy of that hour in Wh.
"""

import pandas as pd
from pydantic import BaseModel, ConfigDict

from loadcurve.domain.models import (
    DAYS_IN_MONTH,
    HOURS_PER_DAY,
    AnalysisSettings,
    LoadTable,
)

WH_PER_KWH = 1000.0
ALL_HOURS: tuple[int, ...] = tuple(range(HOURS_PER_DAY))
DEFAULT_SETTINGS = AnalysisSettings()


class PeriodStats(BaseModel):
    """Power and energy figures over one set of hours of a typical day."""

    model_config = ConfigDict(frozen=True)

    hours: int
    energy_kwh: float
    mean_power_w: float
    peak_power_w: float
    peak_hour: int
    base_power_w: float
    base_hour: int
    load_factor: float  # mean / peak, from 0 to 1; 0 when nothing runs in the period


class LoadHourlyPower(BaseModel):
    """The average power one Load draws in each hour of the day."""

    model_config = ConfigDict(frozen=True)

    name: str
    hourly_power_w: tuple[float, ...]


class MonthlyEnergy(BaseModel):
    """Energy consumed in one month, after its Seasonal multiplier."""

    model_config = ConfigDict(frozen=True)

    month: int  # 1 = January
    days: int
    seasonal_multiplier: float
    energy_kwh: float
    daytime_energy_kwh: float
    nighttime_energy_kwh: float


class LoadAnalysis(BaseModel):
    """Everything the tool derives from a Load table and its Analysis settings."""

    model_config = ConfigDict(frozen=True)

    hourly_profile_w: tuple[float, ...]
    load_duration_curve_w: tuple[float, ...]
    daytime_hours: tuple[int, ...]
    loads: tuple[LoadHourlyPower, ...]
    whole_day: PeriodStats
    daytime: PeriodStats
    nighttime: PeriodStats
    monthly: tuple[MonthlyEnergy, ...]
    annual_energy_kwh: float
    annual_daytime_energy_kwh: float
    annual_nighttime_energy_kwh: float


def analyze(load_table: LoadTable, settings: AnalysisSettings = DEFAULT_SETTINGS) -> LoadAnalysis:
    """Compute the Hourly profile, Load duration curve, period stats and Monthly energy."""
    per_load = _hourly_power_per_load(load_table)
    profile = per_load.sum(axis="index")

    window = settings.daytime_window
    daytime = _period_stats(profile, window.daytime_hours())
    nighttime = _period_stats(profile, window.nighttime_hours())
    monthly = _monthly_energy(
        daytime.energy_kwh, nighttime.energy_kwh, settings.seasonal_multipliers
    )

    return LoadAnalysis(
        hourly_profile_w=tuple(profile),
        load_duration_curve_w=tuple(profile.sort_values(ascending=False)),
        daytime_hours=window.daytime_hours(),
        loads=tuple(
            LoadHourlyPower(name=str(name), hourly_power_w=tuple(row))
            for name, row in per_load.iterrows()
        ),
        whole_day=_period_stats(profile, ALL_HOURS),
        daytime=daytime,
        nighttime=nighttime,
        monthly=monthly,
        annual_energy_kwh=sum(month.energy_kwh for month in monthly),
        annual_daytime_energy_kwh=sum(month.daytime_energy_kwh for month in monthly),
        annual_nighttime_energy_kwh=sum(month.nighttime_energy_kwh for month in monthly),
    )


def _hourly_power_per_load(load_table: LoadTable) -> pd.DataFrame:
    """One row per Load, one column per hour: schedule flag x rated power x usage factor."""
    names = [load.name for load in load_table.loads]
    schedules = pd.DataFrame(
        [load.schedule for load in load_table.loads], index=names, columns=ALL_HOURS
    )
    effective_power_w = pd.Series(
        [load.rated_power_w * load.usage_factor for load in load_table.loads], index=names
    )
    return schedules.mul(effective_power_w, axis="index").astype(float)


def _period_stats(profile: pd.Series, hours: tuple[int, ...]) -> PeriodStats:
    """Stats over ``hours``; on ties, the peak and base hours are the first chronologically."""
    period = profile.loc[list(hours)]
    energy_wh = float(period.sum())
    mean_w = energy_wh / len(hours)
    peak_w = float(period.max())

    return PeriodStats(
        hours=len(hours),
        energy_kwh=energy_wh / WH_PER_KWH,
        mean_power_w=mean_w,
        peak_power_w=peak_w,
        peak_hour=int(period.idxmax()),
        base_power_w=float(period.min()),
        base_hour=int(period.idxmin()),
        load_factor=mean_w / peak_w if peak_w > 0 else 0.0,
    )


def _monthly_energy(
    daytime_kwh_per_day: float,
    nighttime_kwh_per_day: float,
    seasonal_multipliers: tuple[float, ...],
) -> tuple[MonthlyEnergy, ...]:
    months = []
    for index, (days, multiplier) in enumerate(
        zip(DAYS_IN_MONTH, seasonal_multipliers, strict=True)
    ):
        daytime_kwh = daytime_kwh_per_day * days * multiplier
        nighttime_kwh = nighttime_kwh_per_day * days * multiplier
        months.append(
            MonthlyEnergy(
                month=index + 1,
                days=days,
                seasonal_multiplier=multiplier,
                energy_kwh=daytime_kwh + nighttime_kwh,
                daytime_energy_kwh=daytime_kwh,
                nighttime_energy_kwh=nighttime_kwh,
            )
        )
    return tuple(months)
