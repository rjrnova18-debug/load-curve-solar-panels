"""HTTP routes under the /api prefix.

Routes only translate between HTTP and the domain and file modules. Errors use
stable codes the frontend translates:

* 422 (request validation): FastAPI's default body; ``detail[].type`` is the code.
* 400 / 413 / 502 (everything else): ``{"detail": {"code": "<code>", ...}}``.
"""

from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status

from loadcurve.api.dependencies import get_http_client
from loadcurve.api.schemas import AnalysisRequest, AnalysisResponse
from loadcurve.domain.analysis import analyze
from loadcurve.domain.models import LoadTable
from loadcurve.domain.sizing import size_systems
from loadcurve.files.load_table_io import (
    FileFormat,
    ImportResult,
    LoadTableFileError,
    read_load_table,
    write_load_table,
)
from loadcurve.files.sample import template
from loadcurve.solar.pvgis import PvgisError, PvgisLookup, fetch_solar_resource

router = APIRouter(prefix="/api")

MAX_UPLOAD_BYTES = 1_000_000
MEDIA_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
# PVGIS errors caused by the location the user chose; any other code means PVGIS failed.
LOCATION_ERRORS = frozenset({"location_over_sea", "invalid_location"})

Format = Annotated[FileFormat, Query(alias="format")]


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the service is up; used by tests, CI and the hosting platform."""
    return {"status": "ok"}


@router.post("/analysis")
def run_analysis(request: AnalysisRequest) -> AnalysisResponse:
    """Analyse a Load table and, if a Solar resource is given, size the three System types."""
    return evaluate(request)


@router.get("/solar-resource")
def solar_resource(
    lat: Annotated[float, Query(ge=-90, le=90, description="Latitude in decimal degrees.")],
    lon: Annotated[float, Query(ge=-180, le=180, description="Longitude in decimal degrees.")],
    client: Annotated[httpx2.Client, Depends(get_http_client)],
) -> PvgisLookup:
    """Look up the monthly Peak sun hours of a location in PVGIS."""
    try:
        return fetch_solar_resource(lat, lon, client)
    except PvgisError as error:
        code = (
            status.HTTP_400_BAD_REQUEST
            if error.code in LOCATION_ERRORS
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, detail={"code": error.code}) from error


@router.post("/load-table/import")
def import_load_table(file: UploadFile) -> ImportResult:
    """Read a CSV/XLSX Load table; invalid rows are skipped and listed in ``issues``."""
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, detail={"code": "file_too_large"})
    try:
        return read_load_table(content, file.filename or "")
    except LoadTableFileError as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={"code": error.code, "columns": list(error.columns)},
        ) from error


@router.post("/load-table/export")
def export_load_table(load_table: LoadTable, fmt: Format = "xlsx") -> Response:
    """Download a Load table as CSV or XLSX."""
    return file_response(write_load_table(load_table, fmt), "load-table", fmt)


@router.get("/load-table/template")
def load_table_template(fmt: Format = "xlsx") -> Response:
    """Download the sample Load table to fill in."""
    return file_response(template(fmt), "load-table-template", fmt)


def evaluate(request: AnalysisRequest) -> AnalysisResponse:
    """Run the analysis, and the sizing when the request carries a Solar resource."""
    analysis = analyze(request.load_table, request.settings)
    sizing = (
        size_systems(analysis, request.solar_resource, request.assumptions)
        if request.solar_resource is not None
        else None
    )
    return AnalysisResponse(analysis=analysis, sizing=sizing)


def file_response(content: bytes, stem: str, fmt: str) -> Response:
    """A downloadable file: the browser saves it as ``<stem>.<fmt>``."""
    return Response(
        content,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{stem}.{fmt}"'},
    )
