from loadcurve.domain.calculation import ceiling, constant, over, plus, step, times, value
from loadcurve.files.formula_text import expression_text, step_text, symbol_text

ARRAY = over(
    plus(
        value("daytime_energy", 87.62, "kWh"),
        over(value("nighttime_energy", 65.04, "kWh"), value("battery_efficiency", 0.95)),
    ),
    times(value("peak_sun_hours", 4.5, "h", "year"), value("performance_ratio", 0.75)),
)


def test_symbols_carry_their_qualifier() -> None:
    assert symbol_text(value("peak_sun_hours", 4.5, "h", "year")) == "PSH_year"
    assert symbol_text(value("peak_sun_hours", 3.8, "h", "month:6")) == "PSH_Jun"
    assert symbol_text(value("nighttime_energy", 65, "kWh", "max")) == "E_night,max"


def test_symbolic_and_numeric_forms() -> None:
    assert expression_text(ARRAY, numbers=False) == "(E_day + E_night ÷ η) ÷ (PSH_year × PR)"
    assert expression_text(ARRAY, numbers=True) == (
        "(87.62 kWh + 65.04 kWh ÷ 0.95) ÷ (4.50 h × 0.75)"
    )


def test_constants_show_as_numbers_in_both_forms() -> None:
    panels = ceiling(
        over(
            times(value("array_power", 46.25, "kWp"), constant(1000)),
            value("panel_power", 550, "W"),
        )
    )

    assert expression_text(panels, numbers=False) == "⌈(P_array × 1000) ÷ P_panel⌉"
    assert expression_text(panels, numbers=True) == "⌈(46.25 kWp × 1000) ÷ 550 W⌉"


def test_a_step_reads_from_name_to_result() -> None:
    battery = step(
        "battery_capacity",
        over(value("nighttime_energy", 65.04, "kWh", "max"), times(constant(0.8), constant(0.95))),
        "kWh",
    )

    assert step_text(battery) == (
        "C_battery = E_night,max ÷ (0.80 × 0.95) = 65.04 kWh ÷ (0.80 × 0.95) = 85.58 kWh"
    )
