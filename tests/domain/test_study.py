from loadcurve.domain.analysis import analyze
from loadcurve.domain.models import Load, LoadTable, SolarResource
from loadcurve.domain.study import Study, run_study

TABLE = LoadTable(loads=[Load(name="Fridge", rated_power_w=350, schedule=[1] * 24)])


def test_without_solar_resource_there_is_no_sizing() -> None:
    result = run_study(Study(load_table=TABLE))

    assert result.analysis == analyze(TABLE)
    assert result.sizing is None


def test_with_solar_resource_the_three_systems_are_sized() -> None:
    result = run_study(
        Study(load_table=TABLE, solar_resource=SolarResource(peak_sun_hours=[5.0] * 12))
    )

    assert result.sizing is not None
    assert result.sizing.off_grid is not None


def test_a_study_survives_a_json_round_trip() -> None:
    # The browser saves a Study as a project file and sends it back later.
    study = Study(load_table=TABLE, solar_resource=SolarResource(peak_sun_hours=[4.5] * 12))

    assert Study.model_validate_json(study.model_dump_json()) == study
