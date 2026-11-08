"""PVGIS adapter tests. No test touches the network: every response comes from a
``MockTransport`` handler. The happy path replays a real PVGIS v5.3 answer for Bogotá.
"""

import json
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest

from loadcurve.solar.pvgis import PvgisError, fetch_solar_resource

BOGOTA = json.loads((Path(__file__).parent / "pvgis_bogota.json").read_text(encoding="utf-8"))

Handler = Callable[[httpx2.Request], httpx2.Response]


def fake_client(handler: Handler) -> httpx2.Client:
    """An HTTP client whose 'network' is the given function."""
    return httpx2.Client(transport=httpx2.MockTransport(handler))


def respond(status: int, **kwargs) -> Handler:
    return lambda request: httpx2.Response(status, **kwargs)


def lookup_error(handler: Handler) -> str:
    with pytest.raises(PvgisError) as excinfo:
        fetch_solar_resource(4.711, -74.072, fake_client(handler))
    return excinfo.value.code


class TestSuccessfulLookup:
    def test_reads_the_monthly_peak_sun_hours(self) -> None:
        lookup = fetch_solar_resource(4.711, -74.072, fake_client(respond(200, json=BOGOTA)))

        assert lookup.solar_resource.peak_sun_hours == (
            5.09, 5.12, 4.57, 4.18, 3.95, 3.81, 3.87, 4.57, 5.25, 4.84, 4.6, 4.95,
        )  # fmt: skip

    def test_reads_the_optimal_orientation_and_elevation(self) -> None:
        lookup = fetch_solar_resource(4.711, -74.072, fake_client(respond(200, json=BOGOTA)))

        assert (lookup.optimal_slope_deg, lookup.optimal_azimuth_deg) == (7, 14)
        assert lookup.elevation_m == 2555

    def test_asks_pvgis_for_the_location_with_optimal_angles(self) -> None:
        sent: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            sent.append(request)
            return httpx2.Response(200, json=BOGOTA)

        fetch_solar_resource(4.711, -74.072, fake_client(handler))

        params = sent[0].url.params
        assert sent[0].url.path == "/api/v5_3/PVcalc"
        assert (params["lat"], params["lon"]) == ("4.711", "-74.072")
        assert (params["optimalangles"], params["outputformat"]) == ("1", "json")


class TestLocationErrors:
    def test_point_over_the_sea(self) -> None:
        # Real PVGIS answer for lat=0, lon=-140.
        message = {
            "message": "Location over the sea. Please, select another location",
            "status": 400,
        }

        assert lookup_error(respond(400, json=message)) == "location_over_sea"

    def test_coordinates_pvgis_rejects(self) -> None:
        message = {"message": "lat: Incorrect value. Please, enter a float between -90 and 90."}

        assert lookup_error(respond(400, json=message)) == "invalid_location"


class TestServiceErrors:
    def test_timeout(self) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ReadTimeout("PVGIS took too long", request=request)

        assert lookup_error(handler) == "pvgis_unavailable"

    def test_connection_failure(self) -> None:
        def handler(request: httpx2.Request) -> httpx2.Response:
            raise httpx2.ConnectError("no route to host", request=request)

        assert lookup_error(handler) == "pvgis_unavailable"

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_server_side_errors(self, status: int) -> None:
        assert lookup_error(respond(status, text="busy")) == "pvgis_unavailable"


class TestUnexpectedResponses:
    def test_body_is_not_json(self) -> None:
        assert lookup_error(respond(200, text="<html>maintenance</html>")) == (
            "pvgis_unexpected_response"
        )

    def test_monthly_data_is_missing(self) -> None:
        assert lookup_error(respond(200, json={"inputs": BOGOTA["inputs"]})) == (
            "pvgis_unexpected_response"
        )

    def test_a_month_is_missing(self) -> None:
        eleven_months = json.loads(json.dumps(BOGOTA))
        eleven_months["outputs"]["monthly"]["fixed"].pop()

        assert lookup_error(respond(200, json=eleven_months)) == "pvgis_unexpected_response"

    def test_sun_hours_out_of_range(self) -> None:
        impossible = json.loads(json.dumps(BOGOTA))
        impossible["outputs"]["monthly"]["fixed"][0]["H(i)_d"] = -1

        assert lookup_error(respond(200, json=impossible)) == "pvgis_unexpected_response"
