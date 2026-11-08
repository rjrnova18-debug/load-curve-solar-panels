"""Request and response bodies of the HTTP API that are not domain types themselves."""

from pydantic import BaseModel, ConfigDict

from loadcurve.domain.analysis import LoadAnalysis
from loadcurve.domain.models import AnalysisSettings, LoadTable, SizingAssumptions, SolarResource
from loadcurve.domain.sizing import SizingComparison


class AnalysisRequest(BaseModel):
    """Everything the browser holds for one site (the app is stateless, see ADR 0001)."""

    model_config = ConfigDict(frozen=True)

    load_table: LoadTable
    settings: AnalysisSettings = AnalysisSettings()
    solar_resource: SolarResource | None = None
    assumptions: SizingAssumptions = SizingAssumptions()


class AnalysisResponse(BaseModel):
    """The Load analysis, plus the System sizings when a Solar resource was given."""

    model_config = ConfigDict(frozen=True)

    analysis: LoadAnalysis
    sizing: SizingComparison | None
