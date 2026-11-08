import pytest
from pydantic import ValidationError

from loadcurve.domain.models import AnalysisSettings, DaytimeWindow, Load, LoadTable

ALWAYS_ON = [1] * 24


def make_load(**overrides) -> Load:
    fields = {"name": "Fridge", "rated_power_w": 350, "schedule": ALWAYS_ON} | overrides
    return Load(**fields)


def error_type(excinfo: pytest.ExceptionInfo[ValidationError]) -> str:
    return excinfo.value.errors()[0]["type"]


class TestLoad:
    def test_usage_factor_defaults_to_full_hour(self) -> None:
        assert make_load().usage_factor == 1.0

    def test_name_is_trimmed(self) -> None:
        assert make_load(name="  Fridge  ").name == "Fridge"

    def test_accepts_float_flags_as_read_from_spreadsheets(self) -> None:
        assert make_load(schedule=[1.0] * 24).schedule == (1,) * 24

    @pytest.mark.parametrize(
        ("overrides", "expected_error"),
        [
            ({"name": "   "}, "string_too_short"),
            ({"rated_power_w": 0}, "greater_than"),
            ({"rated_power_w": -100}, "greater_than"),
            ({"usage_factor": 1.2}, "less_than_equal"),
            ({"usage_factor": -0.1}, "greater_than_equal"),
            ({"schedule": [1] * 23}, "too_short"),
            ({"schedule": [1] * 25}, "too_long"),
            ({"schedule": [2] + [1] * 23}, "literal_error"),
            ({"schedule": ["on"] * 24}, "literal_error"),
        ],
    )
    def test_rejects_invalid_fields(self, overrides: dict, expected_error: str) -> None:
        with pytest.raises(ValidationError) as excinfo:
            make_load(**overrides)

        assert error_type(excinfo) == expected_error


class TestLoadTable:
    def test_rejects_an_empty_table(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            LoadTable(loads=[])

        assert error_type(excinfo) == "too_short"

    def test_rejects_duplicate_names_ignoring_case(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            LoadTable(loads=[make_load(name="Fridge"), make_load(name="fridge")])

        assert error_type(excinfo) == "duplicate_load_name"


class TestDaytimeWindow:
    def test_default_is_six_to_eighteen(self) -> None:
        window = DaytimeWindow()

        assert window.daytime_hours() == tuple(range(6, 18))
        assert window.nighttime_hours() == (18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5)

    def test_window_can_cross_midnight(self) -> None:
        window = DaytimeWindow(start_hour=22, end_hour=6)

        assert window.daytime_hours() == (22, 23, 0, 1, 2, 3, 4, 5)
        assert window.nighttime_hours() == tuple(range(6, 22))

    @pytest.mark.parametrize(("start", "end"), [(6, 18), (22, 6), (0, 23), (23, 0)])
    def test_day_and_night_cover_every_hour_exactly_once(self, start: int, end: int) -> None:
        window = DaytimeWindow(start_hour=start, end_hour=end)

        hours = window.daytime_hours() + window.nighttime_hours()

        assert sorted(hours) == list(range(24))

    def test_rejects_equal_start_and_end(self) -> None:
        # The legacy app silently treated this as "24 h of day, no night".
        with pytest.raises(ValidationError) as excinfo:
            DaytimeWindow(start_hour=7, end_hour=7)

        assert error_type(excinfo) == "empty_daytime_window"


class TestAnalysisSettings:
    def test_defaults(self) -> None:
        settings = AnalysisSettings()

        assert settings.daytime_window == DaytimeWindow(start_hour=6, end_hour=18)
        assert settings.seasonal_multipliers == (1.0,) * 12

    def test_requires_one_multiplier_per_month(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            AnalysisSettings(seasonal_multipliers=[1.0] * 11)

        assert error_type(excinfo) == "too_short"

    def test_rejects_negative_multipliers(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            AnalysisSettings(seasonal_multipliers=[-0.5] + [1.0] * 11)

        assert error_type(excinfo) == "greater_than_equal"
