"""Calculation steps as plain text, for the Excel report (English).

The browser draws the same trees as MathML fractions; this is the second
renderer of ``loadcurve.domain.calculation``.
"""

from calendar import month_abbr

from loadcurve.domain.calculation import (
    CalculationStep,
    Ceiling,
    Expression,
    Fraction,
    Product,
    Sum,
    Value,
)

SYMBOLS = {
    "daily_energy": "E",
    "daytime_energy": "E_day",
    "nighttime_energy": "E_night",
    "coverage": "c",
    "peak_sun_hours": "PSH",
    "performance_ratio": "PR",
    "battery_efficiency": "η",
    "depth_of_discharge": "DoD",
    "days_of_autonomy": "n_autonomy",
    "array_power": "P_array",
    "panel_power": "P_panel",
    "panel_count": "N",
    "peak_power": "P_peak",
    "seasonal_multiplier": "k_season",
    "inverter_safety_factor": "f",
}

QUANTITIES = {
    "array_power": "P_array",
    "panel_count": "N_panels",
    "battery_capacity": "C_battery",
    "inverter_power": "P_inverter",
}


def symbol_text(value: Value) -> str:
    """``PSH_year``, ``E_night,max``, ``PSH_Jun``…"""
    base = SYMBOLS.get(value.symbol or "", value.symbol or "")
    if not value.qualifier:
        return base
    if value.qualifier.startswith("month:"):
        qualifier = month_abbr[int(value.qualifier.removeprefix("month:"))]
    else:
        qualifier = value.qualifier
    return f"{base}{',' if '_' in base else '_'}{qualifier}"


def number_text(number: float, unit: str = "") -> str:
    text = f"{number:.0f}" if float(number).is_integer() else f"{number:.2f}"
    return f"{text} {unit}".strip()


def expression_text(expression: Expression, *, numbers: bool) -> str:
    """The expression with symbols (``numbers=False``) or with its values."""

    def draw(node: Expression) -> str:
        match node:
            case Value(symbol=None):
                return number_text(node.value)
            case Value():
                return number_text(node.value, node.unit) if numbers else symbol_text(node)
            case Product(terms=terms):
                return " × ".join(wrapped(term) for term in terms)
            case Fraction(numerator=numerator, denominator=denominator):
                return f"{wrapped(numerator)} ÷ {wrapped(denominator)}"
            case Sum(terms=terms):
                return " + ".join(draw(term) for term in terms)
            case Ceiling(argument=argument):
                return f"⌈{draw(argument)}⌉"
        raise TypeError(f"Unknown expression: {node!r}")

    def wrapped(node: Expression) -> str:
        """Parentheses around anything that is not a single value."""
        return draw(node) if isinstance(node, (Value, Ceiling)) else f"({draw(node)})"

    return draw(expression)


def step_text(calculation: CalculationStep) -> str:
    """``P_array = (E_day + …) ÷ (PSH_year × PR) = (… ) ÷ (…) = 46.25 kWp``"""
    name = QUANTITIES[calculation.quantity]
    return " = ".join(
        (
            name,
            expression_text(calculation.expression, numbers=False),
            expression_text(calculation.expression, numbers=True),
            number_text(calculation.result, calculation.unit),
        )
    )
