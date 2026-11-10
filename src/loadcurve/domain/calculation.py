"""Worked calculations: each sizing formula as a small expression tree.

The sizing module builds these trees and gets its numbers by evaluating them, so
the formula shown to the user is, by construction, the one that produced the
result. Renderers (MathML in the browser, plain text in the Excel report) only
draw the tree; they know nothing about panels or batteries.

Symbols are language-neutral keys (``peak_sun_hours``); each renderer maps them
to what its reader sees ("PSH", "HSP").
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# Rounding before a ceiling stops float noise (16.0000000001) from adding a unit.
CEILING_DECIMALS = 6

Quantity = Literal["array_power", "panel_count", "battery_capacity", "inverter_power"]


class Value(BaseModel):
    """A named input (``symbol``) or, with no symbol, a plain constant such as 1000."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["value"] = "value"
    symbol: str | None
    qualifier: str | None = None  # "year", "max", "month:6"
    value: float
    unit: str = ""


class Product(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["product"] = "product"
    terms: tuple[Expression, ...]


class Fraction(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["fraction"] = "fraction"
    numerator: Expression
    denominator: Expression


class Sum(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["sum"] = "sum"
    terms: tuple[Expression, ...]


class Ceiling(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["ceiling"] = "ceiling"
    argument: Expression


Expression = Annotated[Value | Product | Fraction | Sum | Ceiling, Field(discriminator="kind")]

for _model in (Product, Fraction, Sum, Ceiling):
    _model.model_rebuild()


class CalculationStep(BaseModel):
    """One formula of a System sizing: what it computes, how, and the result."""

    model_config = ConfigDict(frozen=True)

    quantity: Quantity
    expression: Expression
    result: float
    unit: str


def evaluate(expression: Expression) -> float:
    """The number an expression tree stands for."""
    match expression:
        case Value(value=value):
            return value
        case Product(terms=terms):
            return math.prod(evaluate(term) for term in terms)
        case Fraction(numerator=numerator, denominator=denominator):
            return evaluate(numerator) / evaluate(denominator)
        case Sum(terms=terms):
            return sum(evaluate(term) for term in terms)
        case Ceiling(argument=argument):
            return float(math.ceil(round(evaluate(argument), CEILING_DECIMALS)))
    raise TypeError(f"Unknown expression: {expression!r}")


def step(quantity: Quantity, expression: Expression, unit: str) -> CalculationStep:
    """A calculation step whose result is its own expression, evaluated."""
    return CalculationStep(
        quantity=quantity, expression=expression, result=evaluate(expression), unit=unit
    )


# ---------- Builders, so formulas read like formulas in the sizing module ----------


def value(symbol: str, number: float, unit: str = "", qualifier: str | None = None) -> Value:
    return Value(symbol=symbol, value=number, unit=unit, qualifier=qualifier)


def constant(number: float) -> Value:
    return Value(symbol=None, value=number)


def times(*terms: Expression) -> Product:
    return Product(terms=terms)


def over(numerator: Expression, denominator: Expression) -> Fraction:
    return Fraction(numerator=numerator, denominator=denominator)


def plus(*terms: Expression) -> Sum:
    return Sum(terms=terms)


def ceiling(argument: Expression) -> Ceiling:
    return Ceiling(argument=argument)
