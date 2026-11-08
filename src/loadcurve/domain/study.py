"""A Study: everything the user enters for one site, and what the tool derives from it.

``run_study`` is the single entry point that the API and the report share. A saved
project file is a Study serialized as JSON (the app keeps no state, see ADR 0001).
"""

from pydantic import BaseModel, ConfigDict

from loadcurve.domain.analysis import LoadAnalysis, analyze
from loadcurve.domain.models import AnalysisSettings, LoadTable, SizingAssumptions, SolarResource
from loadcurve.domain.sizing import SizingComparison, size_systems


class Study(BaseModel):
    """The inputs for one site. Sizing needs a Solar resource; the rest has defaults."""

    model_config = ConfigDict(frozen=True)

    load_table: LoadTable
    settings: AnalysisSettings = AnalysisSettings()
    solar_resource: SolarResource | None = None
    assumptions: SizingAssumptions = SizingAssumptions()


class StudyResult(BaseModel):
    """The Load analysis, plus the System sizings when the Study has a Solar resource."""

    model_config = ConfigDict(frozen=True)

    analysis: LoadAnalysis
    sizing: SizingComparison | None


def run_study(study: Study) -> StudyResult:
    """Analyse the Load table and, when the Study has a Solar resource, size the systems."""
    analysis = analyze(study.load_table, study.settings)
    sizing = (
        size_systems(analysis, study.solar_resource, study.assumptions)
        if study.solar_resource is not None
        else None
    )
    return StudyResult(analysis=analysis, sizing=sizing)
