"""Domain types and their validation rules.

Every rule lives here, once, and applies equally to JSON requests and to rows
imported from CSV/XLSX files (see ADR 0002). Custom rule violations raise
``PydanticCustomError`` with a stable error type (e.g. ``duplicate_load_name``)
that the frontend translates.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

HOURS_PER_DAY = 24
MONTHS_PER_YEAR = 12
# Non-leap year: the tool produces estimates, not billing-grade figures.
DAYS_IN_MONTH: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

MIN_SEASONAL_MULTIPLIER = 0.0
MAX_SEASONAL_MULTIPLIER = 3.0

HourFlag = Literal[0, 1]
Schedule = Annotated[
    tuple[HourFlag, ...],
    Field(min_length=HOURS_PER_DAY, max_length=HOURS_PER_DAY),
]
SeasonalMultipliers = Annotated[
    tuple[Annotated[float, Field(ge=MIN_SEASONAL_MULTIPLIER, le=MAX_SEASONAL_MULTIPLIER)], ...],
    Field(min_length=MONTHS_PER_YEAR, max_length=MONTHS_PER_YEAR),
]


class Load(BaseModel):
    """A single piece of electrical equipment."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    rated_power_w: float = Field(gt=0, description="Power drawn while running, in watts.")
    usage_factor: float = Field(
        default=1.0,
        ge=0,
        le=1,
        description="Fraction of each switched-on hour in which the Load draws its rated power.",
    )
    schedule: Schedule = Field(description="24 on/off flags, one per hour (0 to 23).")


class LoadTable(BaseModel):
    """The full set of Loads entered for one site. Load names are unique."""

    model_config = ConfigDict(frozen=True)

    loads: tuple[Load, ...] = Field(min_length=1)

    @field_validator("loads")
    @classmethod
    def _names_are_unique(cls, loads: tuple[Load, ...]) -> tuple[Load, ...]:
        seen: set[str] = set()
        for load in loads:
            key = load.name.casefold()
            if key in seen:
                raise PydanticCustomError(
                    "duplicate_load_name",
                    "Load name '{name}' is used more than once",
                    {"name": load.name},
                )
            seen.add(key)
        return loads


class DaytimeWindow(BaseModel):
    """Hours that count as day: from ``start_hour`` (inclusive) to ``end_hour`` (exclusive).

    The window may cross midnight (e.g. 22 -> 6). Every other hour counts as night.
    """

    model_config = ConfigDict(frozen=True)

    start_hour: int = Field(default=6, ge=0, le=HOURS_PER_DAY - 1)
    end_hour: int = Field(default=18, ge=0, le=HOURS_PER_DAY - 1)

    @model_validator(mode="after")
    def _day_and_night_are_both_present(self) -> "DaytimeWindow":
        if self.start_hour == self.end_hour:
            raise PydanticCustomError(
                "empty_daytime_window",
                "Daytime start and end hours must differ",
            )
        return self

    def daytime_hours(self) -> tuple[int, ...]:
        """Daytime hours in chronological order, starting at ``start_hour``."""
        return _hours_between(self.start_hour, self.end_hour)

    def nighttime_hours(self) -> tuple[int, ...]:
        """Night-time hours in chronological order, starting at ``end_hour``."""
        return _hours_between(self.end_hour, self.start_hour)


def _hours_between(start: int, end: int) -> tuple[int, ...]:
    """Hours from ``start`` up to, but not including, ``end``, wrapping past midnight."""
    length = (end - start) % HOURS_PER_DAY
    return tuple((start + offset) % HOURS_PER_DAY for offset in range(length))


class AnalysisSettings(BaseModel):
    """User choices that shape the analysis of a Load table."""

    model_config = ConfigDict(frozen=True)

    daytime_window: DaytimeWindow = DaytimeWindow()
    seasonal_multipliers: SeasonalMultipliers = (1.0,) * MONTHS_PER_YEAR
