import io

import pytest
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from loadcurve.domain.models import Load, LoadTable, SolarResource
from loadcurve.domain.study import Study, run_study
from loadcurve.files.report import NOT_FEASIBLE, build_report

FRIDGE = LoadTable(loads=[Load(name="Fridge", rated_power_w=1000, schedule=[1] * 24)])
SUNNY = SolarResource(peak_sun_hours=[5.0] * 12)
POLAR = SolarResource(peak_sun_hours=[1.0] * 11 + [0.0])


def workbook_for(study: Study):
    return load_workbook(io.BytesIO(build_report(study, run_study(study))))


def column(sheet: Worksheet, header: str) -> list:
    headers = [cell.value for cell in sheet[1]]
    index = headers.index(header)
    return [row[index] for row in sheet.iter_rows(min_row=2, values_only=True)]


def row(sheet: Worksheet, first_cell: str) -> list:
    return next(r for r in sheet.iter_rows(values_only=True) if r[0] == first_cell)


def test_without_solar_resource_has_only_the_consumption_sheets() -> None:
    workbook = workbook_for(Study(load_table=FRIDGE))

    assert workbook.sheetnames == [
        "Summary",
        "Loads",
        "Hourly profile",
        "Load duration curve",
        "Monthly energy",
    ]


def test_with_solar_resource_adds_sizing_calculations_and_assumptions() -> None:
    workbook = workbook_for(Study(load_table=FRIDGE, solar_resource=SUNNY))

    assert workbook.sheetnames[-3:] == ["Sizing", "Calculations", "Assumptions"]


def test_summary_holds_daily_and_yearly_energy() -> None:
    summary = workbook_for(Study(load_table=FRIDGE))["Summary"]

    assert row(summary, "Energy per day (kWh)")[1:] == pytest.approx((24, 12, 12))
    assert row(summary, "Energy per year (kWh)")[1] == pytest.approx(24 * 365)


def test_hourly_profile_has_a_column_per_load() -> None:
    sheet = workbook_for(Study(load_table=FRIDGE))["Hourly profile"]

    assert column(sheet, "Hour") == list(range(24))
    assert column(sheet, "Fridge (W)") == [1000] * 24
    assert column(sheet, "Period")[6] == "Daytime"
    assert column(sheet, "Period")[18] == "Night-time"


def test_monthly_energy_names_the_months() -> None:
    sheet = workbook_for(Study(load_table=FRIDGE))["Monthly energy"]

    assert column(sheet, "Month")[0] == "January"
    assert column(sheet, "Energy (kWh)")[1] == pytest.approx(24 * 28)


def test_sizing_compares_the_three_systems() -> None:
    sheet = workbook_for(Study(load_table=FRIDGE, solar_resource=SUNNY))["Sizing"]

    assert [cell.value for cell in sheet[1]] == ["Item", "On-grid", "Hybrid", "Off-grid"]
    assert row(sheet, "Required array power (kWp)")[1] == pytest.approx(24 / (5 * 0.75))
    assert row(sheet, "Battery capacity (kWh)")[1] == 0


def test_unfeasible_off_grid_is_explained() -> None:
    sheet = workbook_for(Study(load_table=FRIDGE, solar_resource=POLAR))["Sizing"]

    assert set(column(sheet, "Off-grid")) == {NOT_FEASIBLE}


def test_calculations_sheet_shows_every_formula_with_its_numbers() -> None:
    sheet = workbook_for(Study(load_table=FRIDGE, solar_resource=SUNNY))["Calculations"]

    assert [cell.value for cell in sheet[1]] == [
        "System",
        "Quantity",
        "Formula",
        "With your numbers",
        "Result",
        "Unit",
    ]
    hybrid_battery = next(
        r for r in sheet.iter_rows(min_row=2, values_only=True) if r[:2] == ("Hybrid", "C_battery")
    )
    assert hybrid_battery[2] == "E_night,max ÷ (DoD × η)"
    assert hybrid_battery[4] == pytest.approx(12 / 0.76)


def test_calculations_sheet_explains_an_unfeasible_off_grid() -> None:
    sheet = workbook_for(Study(load_table=FRIDGE, solar_resource=POLAR))["Calculations"]

    assert NOT_FEASIBLE in column(sheet, "Formula")
