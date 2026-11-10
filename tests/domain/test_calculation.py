import pytest

from loadcurve.domain.calculation import (
    CalculationStep,
    ceiling,
    constant,
    evaluate,
    over,
    plus,
    step,
    times,
    value,
)


def test_evaluates_each_kind_of_node() -> None:
    expression = over(
        plus(
            value("daytime_energy", 12, "kWh"),
            over(value("nighttime_energy", 9.5, "kWh"), constant(0.95)),
        ),
        times(value("peak_sun_hours", 5, "h"), value("performance_ratio", 0.75)),
    )

    assert evaluate(expression) == pytest.approx((12 + 9.5 / 0.95) / (5 * 0.75))


def test_ceiling_ignores_float_noise() -> None:
    # 6.4 x 1000 / 400 is 16.000000000000004 in floating point: still 16 panels.
    assert evaluate(ceiling(over(times(constant(6.4), constant(1000)), constant(400)))) == 16
    assert evaluate(ceiling(constant(16.2))) == 17


def test_a_step_result_is_its_expression_evaluated() -> None:
    calculation = step(
        "battery_capacity", over(constant(12), times(constant(0.8), constant(0.95))), "kWh"
    )

    assert calculation.result == pytest.approx(12 / 0.76)


def test_steps_survive_a_json_round_trip() -> None:
    calculation = step(
        "panel_count",
        ceiling(
            over(
                times(value("array_power", 6.4, "kWp"), constant(1000)),
                value("panel_power", 550, "W"),
            )
        ),
        "",
    )

    assert CalculationStep.model_validate_json(calculation.model_dump_json()) == calculation
