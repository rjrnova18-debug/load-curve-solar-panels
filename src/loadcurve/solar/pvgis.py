"""Solar resource lookup from PVGIS, the EU Joint Research Centre's free solar API.

This module is the adapter between the PVGIS ``PVcalc`` JSON and the domain's
``SolarResource``: it is the only code that knows PVGIS's URL, parameters and
field names. The HTTP client is passed in, so production uses the network and
tests use ``httpx2.MockTransport``.

``H(i)_d`` in the response is the mean daily irradiation of each month on a panel
at the optimal tilt, in kWh/m2/day. Divided by the 1 kW/m2 reference irradiance,
that is exactly the month's Peak sun hours.
"""

from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from loadcurve.domain.models import MONTHS_PER_YEAR, SolarResource

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
TIMEOUT_SECONDS = 20.0

# PVcalc requires a system size and losses to run, but the irradiation we read
# does not depend on them; our own Sizing assumptions apply the losses.
_FIXED_PARAMS = {"peakpower": 1, "loss": 14, "optimalangles": 1, "outputformat": "json"}


class PvgisLookup(BaseModel):
    """The Solar resource of a location, plus the panel orientation PVGIS found optimal."""

    model_config = ConfigDict(frozen=True)

    solar_resource: SolarResource
    optimal_slope_deg: float = Field(description="Panel tilt from horizontal.")
    optimal_azimuth_deg: float = Field(
        description="PVGIS convention: 0 = facing south, 90 = west, -90 = east, 180 = north."
    )
    elevation_m: float


class PvgisError(Exception):
    """PVGIS could not provide a Solar resource. ``code`` is a stable error type."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fetch_solar_resource(latitude: float, longitude: float, client: httpx2.Client) -> PvgisLookup:
    """Ask PVGIS for the monthly Peak sun hours at a location.

    Raises ``PvgisError`` with one of: ``location_over_sea``, ``invalid_location``,
    ``pvgis_unavailable`` or ``pvgis_unexpected_response``.
    """
    payload = _request(latitude, longitude, client)
    return _parse(payload)


def _request(latitude: float, longitude: float, client: httpx2.Client) -> Any:
    """Call PVGIS and return the decoded JSON, translating every failure into a code."""
    params = {"lat": latitude, "lon": longitude, **_FIXED_PARAMS}
    try:
        response = client.get(PVGIS_URL, params=params, timeout=TIMEOUT_SECONDS)
    except httpx2.RequestError as error:  # timeouts, DNS and connection failures
        raise PvgisError("pvgis_unavailable") from error

    if response.status_code == httpx2.codes.BAD_REQUEST:
        # PVGIS answers 400 with a human message, e.g. "Location over the sea. ..."
        if "sea" in _error_message(response).casefold():
            raise PvgisError("location_over_sea")
        raise PvgisError("invalid_location")
    if response.is_error:  # rate limits and server errors: worth retrying later
        raise PvgisError("pvgis_unavailable")

    try:
        return response.json()
    except ValueError as error:
        raise PvgisError("pvgis_unexpected_response") from error


def _error_message(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("message", ""))
    except (ValueError, AttributeError):
        return response.text


def _parse(payload: Any) -> PvgisLookup:
    """Read the twelve monthly ``H(i)_d`` values and the optimal mounting angles."""
    try:
        monthly = payload["outputs"]["monthly"]["fixed"]
        sun_hours_by_month = {entry["month"]: entry["H(i)_d"] for entry in monthly}
        peak_sun_hours = tuple(sun_hours_by_month[month] for month in range(1, MONTHS_PER_YEAR + 1))
        mounting = payload["inputs"]["mounting_system"]["fixed"]
        return PvgisLookup(
            solar_resource=SolarResource(peak_sun_hours=peak_sun_hours),
            optimal_slope_deg=mounting["slope"]["value"],
            optimal_azimuth_deg=mounting["azimuth"]["value"],
            elevation_m=payload["inputs"]["location"]["elevation"],
        )
    except (KeyError, TypeError, ValidationError) as error:
        raise PvgisError("pvgis_unexpected_response") from error
