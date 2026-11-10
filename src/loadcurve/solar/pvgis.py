"""Solar resource lookup from PVGIS, the EU Joint Research Centre's free solar API.

This module is the adapter between the PVGIS ``PVcalc`` JSON and the domain's
``SolarResource``: it is the only code that knows PVGIS's URL, parameters and
field names. The HTTP client is passed in, so production uses the network and
tests use ``httpx2.MockTransport``.

``H(i)_d`` in the response is the mean daily irradiation of each month on a panel
at the optimal tilt, in kWh/m2/day. Divided by the 1 kW/m2 reference irradiance,
that is exactly the month's Peak sun hours.

How it copes with PVGIS's real-world failures (measured in November 2026):

* A dropped connection ("server disconnected without a response") is random and
  usually works on a second try: it is retried once, immediately.
* HTTP 500 is tied to the location (some mountain points always fail). PVGIS is
  asked again without terrain shading, which rescues some of them; if that also
  fails the error is ``pvgis_cannot_compute``, not "try again".
* A request once hung for ten minutes despite the read timeout, so the whole
  lookup runs under an overall deadline.

Every failure is logged with its cause so it shows in the server's terminal.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as DeadlineExceeded
from typing import Any

import httpx2
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from loadcurve.domain.models import MONTHS_PER_YEAR, SolarResource

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
REQUEST_TIMEOUT_SECONDS = 20.0
DEADLINE_SECONDS = 25.0

# PVcalc requires a system size and losses to run, but the irradiation we read
# does not depend on them; our own Sizing assumptions apply the losses.
_FIXED_PARAMS = {"peakpower": 1, "loss": 14, "optimalangles": 1, "outputformat": "json"}

# Failures that happen before PVGIS answers and usually vanish on a second try.
_TRANSIENT_ERRORS = (httpx2.RemoteProtocolError, httpx2.ConnectError)

logger = logging.getLogger(__name__)

# Lookups run on these threads so a hung request cannot outlive the deadline.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pvgis")


class PvgisLookup(BaseModel):
    """The Solar resource of a location, plus the panel orientation PVGIS found optimal."""

    model_config = ConfigDict(frozen=True)

    solar_resource: SolarResource
    optimal_slope_deg: float = Field(description="Panel tilt from horizontal.")
    optimal_azimuth_deg: float = Field(
        description="PVGIS convention: 0 = facing south, 90 = west, -90 = east, 180 = north."
    )
    elevation_m: float
    horizon_shading: bool = Field(
        default=True,
        description="False when PVGIS could only answer without terrain shading.",
    )


class PvgisError(Exception):
    """PVGIS could not provide a Solar resource. ``code`` is a stable error type."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _ServerError(Exception):
    """PVGIS answered HTTP 500 for this location."""


def fetch_solar_resource(
    latitude: float,
    longitude: float,
    client: httpx2.Client,
    *,
    deadline_seconds: float = DEADLINE_SECONDS,
) -> PvgisLookup:
    """Ask PVGIS for the monthly Peak sun hours at a location.

    Raises ``PvgisError`` with one of: ``location_over_sea``, ``invalid_location``,
    ``pvgis_cannot_compute``, ``pvgis_unavailable`` or ``pvgis_unexpected_response``.
    """
    future = _executor.submit(_lookup, latitude, longitude, client)
    try:
        return future.result(timeout=deadline_seconds)
    except DeadlineExceeded as error:
        logger.warning(
            "PVGIS gave no answer within %ss for lat=%s lon=%s",
            deadline_seconds,
            latitude,
            longitude,
        )
        raise PvgisError("pvgis_unavailable") from error


def _lookup(latitude: float, longitude: float, client: httpx2.Client) -> PvgisLookup:
    """One lookup with terrain shading, and a second one without it after an HTTP 500."""
    try:
        return _parse(_request(latitude, longitude, client, horizon=True), horizon_shading=True)
    except _ServerError:
        logger.warning(
            "PVGIS returned HTTP 500 for lat=%s lon=%s; retrying without terrain shading",
            latitude,
            longitude,
        )
    try:
        return _parse(_request(latitude, longitude, client, horizon=False), horizon_shading=False)
    except _ServerError as error:
        logger.warning("PVGIS cannot compute lat=%s lon=%s (HTTP 500 twice)", latitude, longitude)
        raise PvgisError("pvgis_cannot_compute") from error


def _request(latitude: float, longitude: float, client: httpx2.Client, *, horizon: bool) -> Any:
    """Call PVGIS and return the decoded JSON, translating every failure into a code."""
    params: dict[str, Any] = {"lat": latitude, "lon": longitude, **_FIXED_PARAMS}
    if not horizon:
        params["usehorizon"] = 0
    response = _get_with_one_retry(client, params)

    if response.status_code == httpx2.codes.BAD_REQUEST:
        # PVGIS answers 400 with a human message, e.g. "Location over the sea. ..."
        message = _error_message(response)
        if "sea" in message.casefold():
            raise PvgisError("location_over_sea")
        logger.warning("PVGIS rejected lat=%s lon=%s: %s", latitude, longitude, message)
        raise PvgisError("invalid_location")
    if response.status_code == httpx2.codes.INTERNAL_SERVER_ERROR:
        raise _ServerError()
    if response.is_error:  # rate limits, gateway errors: worth retrying later
        logger.warning(
            "PVGIS answered HTTP %s for lat=%s lon=%s", response.status_code, latitude, longitude
        )
        raise PvgisError("pvgis_unavailable")

    try:
        return response.json()
    except ValueError as error:
        logger.warning("PVGIS sent a body that is not JSON: %.80r", response.text)
        raise PvgisError("pvgis_unexpected_response") from error


def _get_with_one_retry(client: httpx2.Client, params: dict[str, Any]) -> httpx2.Response:
    """GET PVGIS, retrying once, at once, when the connection drops before an answer."""
    try:
        return client.get(PVGIS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except _TRANSIENT_ERRORS as error:
        logger.warning(
            "PVGIS connection failed (%s: %s); retrying once", type(error).__name__, error
        )
    except httpx2.RequestError as error:  # timeouts: retrying would double the wait
        logger.warning("PVGIS request failed: %s: %s", type(error).__name__, error)
        raise PvgisError("pvgis_unavailable") from error
    try:
        return client.get(PVGIS_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    except httpx2.RequestError as error:
        logger.warning("PVGIS failed again: %s: %s", type(error).__name__, error)
        raise PvgisError("pvgis_unavailable") from error


def _error_message(response: httpx2.Response) -> str:
    try:
        return str(response.json().get("message", ""))
    except (ValueError, AttributeError):
        return response.text


def _parse(payload: Any, *, horizon_shading: bool) -> PvgisLookup:
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
            horizon_shading=horizon_shading,
        )
    except (KeyError, TypeError, ValidationError) as error:
        logger.warning("PVGIS answer has an unexpected shape: %s", error)
        raise PvgisError("pvgis_unexpected_response") from error
