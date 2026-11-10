"""The downloadable Excel report of a Study: one sheet per table.

Sheets: Summary, Loads, Hourly profile, Load duration curve, Monthly energy and,
when the Study has a Solar resource, Sizing, Calculations and Assumptions. Values
are raw numbers (no rounding) so the user can keep calculating in Excel.
"""

import io
from calendar import month_name

import pandas as pd

from loadcurve.domain.analysis import LoadAnalysis, PeriodStats
from loadcurve.domain.models import SizingAssumptions, SolarResource
from loadcurve.domain.sizing import SizingComparison, SystemSizing
from loadcurve.domain.study import Study, StudyResult
from loadcurve.files.formula_text import QUANTITIES, expression_text
from loadcurve.files.load_table_io import load_table_frame

NOT_FEASIBLE = "Not feasible: a month with consumption has no sun"


def build_report(study: Study, result: StudyResult) -> bytes:
    """Write the Study and its results to an XLSX workbook."""
    analysis = result.analysis
    sheets: dict[str, pd.DataFrame] = {
        "Summary": _summary(analysis),
        "Loads": load_table_frame(study.load_table),
        "Hourly profile": _hourly_profile(analysis),
        "Load duration curve": _load_duration_curve(analysis),
        "Monthly energy": _monthly_energy(analysis),
    }
    if result.sizing is not None and study.solar_resource is not None:
        sheets["Sizing"] = _sizing(result.sizing)
        sheets["Calculations"] = _calculations(result.sizing)
        sheets["Assumptions"] = _assumptions(study.assumptions, study.solar_resource)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return buffer.getvalue()


def _summary(analysis: LoadAnalysis) -> pd.DataFrame:
    periods: dict[str, PeriodStats] = {
        "Whole day": analysis.whole_day,
        "Daytime": analysis.daytime,
        "Night-time": analysis.nighttime,
    }
    rows = [
        ("Hours", lambda p: p.hours),
        ("Energy per day (kWh)", lambda p: p.energy_kwh),
        ("Mean power (W)", lambda p: p.mean_power_w),
        ("Peak power (W)", lambda p: p.peak_power_w),
        ("Peak hour", lambda p: p.peak_hour),
        ("Base power (W)", lambda p: p.base_power_w),
        ("Base hour", lambda p: p.base_hour),
        ("Load factor", lambda p: p.load_factor),
    ]
    frame = pd.DataFrame(
        [[label, *(read(period) for period in periods.values())] for label, read in rows],
        columns=["Metric", *periods],
    )
    annual = pd.DataFrame(
        [
            [
                "Energy per year (kWh)",
                analysis.annual_energy_kwh,
                analysis.annual_daytime_energy_kwh,
                analysis.annual_nighttime_energy_kwh,
            ]
        ],
        columns=frame.columns,
    )
    return pd.concat([frame, annual], ignore_index=True)


def _hourly_profile(analysis: LoadAnalysis) -> pd.DataFrame:
    daytime = set(analysis.daytime_hours)
    frame = pd.DataFrame(
        {
            "Hour": range(len(analysis.hourly_profile_w)),
            "Period": ["Daytime" if hour in daytime else "Night-time" for hour in range(24)],
            "Total power (W)": analysis.hourly_profile_w,
        }
    )
    for load in analysis.loads:
        frame[f"{load.name} (W)"] = load.hourly_power_w
    return frame


def _load_duration_curve(analysis: LoadAnalysis) -> pd.DataFrame:
    curve = analysis.load_duration_curve_w
    return pd.DataFrame({"Hours at or above": range(1, len(curve) + 1), "Power (W)": curve})


def _monthly_energy(analysis: LoadAnalysis) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Month": [month_name[month.month] for month in analysis.monthly],
            "Days": [month.days for month in analysis.monthly],
            "Seasonal multiplier": [month.seasonal_multiplier for month in analysis.monthly],
            "Energy (kWh)": [month.energy_kwh for month in analysis.monthly],
            "Daytime energy (kWh)": [month.daytime_energy_kwh for month in analysis.monthly],
            "Night-time energy (kWh)": [month.nighttime_energy_kwh for month in analysis.monthly],
        }
    )


def _sizing(sizing: SizingComparison) -> pd.DataFrame:
    systems: dict[str, SystemSizing | None] = {
        "On-grid": sizing.on_grid,
        "Hybrid": sizing.hybrid,
        "Off-grid": sizing.off_grid,
    }
    rows = [
        ("Design month", lambda s: month_name[s.design_month] if s.design_month else "Year"),
        ("Design energy per day (kWh)", lambda s: s.design_daily_energy_kwh),
        ("Design peak sun hours", lambda s: s.design_peak_sun_hours),
        ("Required array power (kWp)", lambda s: s.array_power_kwp),
        ("Panels", lambda s: s.panel_count),
        ("Installed power (kWp)", lambda s: s.installed_power_kwp),
        ("Battery capacity (kWh)", lambda s: s.battery_capacity_kwh),
        ("Inverter power (kW)", lambda s: s.inverter_power_kw),
    ]
    return pd.DataFrame(
        [
            [
                label,
                *(NOT_FEASIBLE if system is None else read(system) for system in systems.values()),
            ]
            for label, read in rows
        ],
        columns=["Item", *systems],
    )


def _calculations(sizing: SizingComparison) -> pd.DataFrame:
    """Every formula behind the Sizing sheet, with symbols and with the numbers used."""
    systems: dict[str, SystemSizing | None] = {
        "On-grid": sizing.on_grid,
        "Hybrid": sizing.hybrid,
        "Off-grid": sizing.off_grid,
    }
    rows = []
    for name, system in systems.items():
        if system is None:
            rows.append([name, "", NOT_FEASIBLE, "", None, ""])
            continue
        for calculation in system.steps:
            rows.append(
                [
                    name,
                    QUANTITIES[calculation.quantity],
                    expression_text(calculation.expression, numbers=False),
                    expression_text(calculation.expression, numbers=True),
                    calculation.result,
                    calculation.unit,
                ]
            )
    return pd.DataFrame(
        rows, columns=["System", "Quantity", "Formula", "With your numbers", "Result", "Unit"]
    )


def _assumptions(assumptions: SizingAssumptions, solar: SolarResource) -> pd.DataFrame:
    parameters = [
        ("Performance ratio", assumptions.performance_ratio),
        ("Panel power (W)", assumptions.panel_power_w),
        ("Battery depth of discharge", assumptions.battery_depth_of_discharge),
        ("Battery efficiency", assumptions.battery_efficiency),
        ("Inverter safety factor", assumptions.inverter_safety_factor),
        ("Days of autonomy", assumptions.days_of_autonomy),
        ("On-grid coverage", assumptions.on_grid_coverage),
    ]
    sun_hours = [
        (f"Peak sun hours, {month_name[index + 1]}", psh)
        for index, psh in enumerate(solar.peak_sun_hours)
    ]
    return pd.DataFrame(parameters + sun_hours, columns=["Parameter", "Value"])
