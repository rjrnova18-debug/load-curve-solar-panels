"""HTTP-level tests: status codes, error codes and wiring. The calculations
themselves are covered by the domain tests."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from loadcurve.api.app import create_app
from loadcurve.api.dependencies import get_http_client
from loadcurve.files.load_table_io import read_load_table, write_load_table
from loadcurve.files.sample import SAMPLE_LOAD_TABLE

BOGOTA = json.loads(
    (Path(__file__).parents[1] / "solar" / "pvgis_bogota.json").read_text(encoding="utf-8")
)
BOGOTA_PSH = [5.09, 5.12, 4.57, 4.18, 3.95, 3.81, 3.87, 4.57, 5.25, 4.84, 4.6, 4.95]
SAMPLE_JSON = SAMPLE_LOAD_TABLE.model_dump(mode="json")
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

PvgisHandler = Callable[[httpx2.Request], httpx2.Response]


@pytest.fixture
def pvgis() -> dict[str, PvgisHandler]:
    """The fake PVGIS behaviour; tests swap ``pvgis["handler"]`` to simulate failures."""
    return {"handler": lambda request: httpx2.Response(200, json=BOGOTA)}


@pytest.fixture
def client(pvgis: dict[str, PvgisHandler]) -> TestClient:
    app = create_app()

    def fake_http_client() -> Iterator[httpx2.Client]:
        transport = httpx2.MockTransport(lambda request: pvgis["handler"](request))
        with httpx2.Client(transport=transport) as http_client:
            yield http_client

    app.dependency_overrides[get_http_client] = fake_http_client
    return TestClient(app)


class TestAnalysis:
    def test_without_solar_resource_returns_only_the_analysis(self, client: TestClient) -> None:
        response = client.post("/api/analysis", json={"load_table": SAMPLE_JSON})

        assert response.status_code == 200
        body = response.json()
        assert len(body["analysis"]["hourly_profile_w"]) == 24
        assert len(body["analysis"]["monthly"]) == 12
        assert body["sizing"] is None

    def test_with_solar_resource_sizes_the_three_system_types(self, client: TestClient) -> None:
        payload = {"load_table": SAMPLE_JSON, "solar_resource": {"peak_sun_hours": BOGOTA_PSH}}

        sizing = client.post("/api/analysis", json=payload).json()["sizing"]

        assert sizing["on_grid"]["system_type"] == "on_grid"
        assert sizing["hybrid"]["battery_capacity_kwh"] > 0
        assert sizing["off_grid"]["design_month"] in range(1, 13)

    def test_settings_and_assumptions_are_applied(self, client: TestClient) -> None:
        payload = {
            "load_table": SAMPLE_JSON,
            "settings": {"daytime_window": {"start_hour": 7, "end_hour": 19}},
            "solar_resource": {"peak_sun_hours": BOGOTA_PSH},
            "assumptions": {"panel_power_w": 400},
        }

        body = client.post("/api/analysis", json=payload).json()

        assert body["analysis"]["daytime_hours"] == list(range(7, 19))
        on_grid = body["sizing"]["on_grid"]
        assert on_grid["installed_power_kwp"] == pytest.approx(on_grid["panel_count"] * 0.4)

    @pytest.mark.parametrize(
        ("change", "expected_code"),
        [
            ({"rated_power_w": -5}, "greater_than"),
            ({"schedule": [1] * 20}, "too_short"),
            ({"name": "Server rack"}, "duplicate_load_name"),
        ],
    )
    def test_invalid_load_tables_return_validation_codes(
        self, client: TestClient, change: dict, expected_code: str
    ) -> None:
        bad_load = {**SAMPLE_JSON["loads"][1], **change}
        payload = {"load_table": {"loads": [SAMPLE_JSON["loads"][0], bad_load]}}

        response = client.post("/api/analysis", json=payload)

        assert response.status_code == 422
        assert [error["type"] for error in response.json()["detail"]] == [expected_code]


class TestSolarResource:
    def test_returns_the_pvgis_lookup(self, client: TestClient) -> None:
        response = client.get("/api/solar-resource", params={"lat": 4.711, "lon": -74.072})

        assert response.status_code == 200
        body = response.json()
        assert body["solar_resource"]["peak_sun_hours"] == BOGOTA_PSH
        assert body["optimal_slope_deg"] == 7

    def test_location_problems_are_client_errors(self, client: TestClient, pvgis: dict) -> None:
        sea = {"message": "Location over the sea. Please, select another location"}
        pvgis["handler"] = lambda request: httpx2.Response(400, json=sea)

        response = client.get("/api/solar-resource", params={"lat": 0, "lon": -140})

        assert response.status_code == 400
        assert response.json()["detail"] == {"code": "location_over_sea"}

    def test_pvgis_failures_are_bad_gateway(self, client: TestClient, pvgis: dict) -> None:
        pvgis["handler"] = lambda request: httpx2.Response(503, text="down")

        response = client.get("/api/solar-resource", params={"lat": 4.711, "lon": -74.072})

        assert response.status_code == 502
        assert response.json()["detail"] == {"code": "pvgis_unavailable"}

    def test_out_of_range_coordinates_never_reach_pvgis(
        self, client: TestClient, pvgis: dict
    ) -> None:
        pvgis["handler"] = lambda request: pytest.fail("PVGIS should not be called")

        response = client.get("/api/solar-resource", params={"lat": 95, "lon": 0})

        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "less_than_equal"


class TestLoadTableImport:
    def test_imports_a_spreadsheet(self, client: TestClient) -> None:
        upload = ("office.xlsx", write_load_table(SAMPLE_LOAD_TABLE, "xlsx"), XLSX_TYPE)

        response = client.post("/api/load-table/import", files={"file": upload})

        assert response.status_code == 200
        assert len(response.json()["loads"]) == len(SAMPLE_LOAD_TABLE.loads)
        assert response.json()["issues"] == []

    def test_reports_row_issues(self, client: TestClient) -> None:
        hours = ",".join(str(h) for h in range(24))
        csv = f"Load,Rated power (W),{hours}\nHeater,-1,{','.join(['1'] * 24)}\n"

        response = client.post("/api/load-table/import", files={"file": ("x.csv", csv)})

        assert response.json()["issues"] == [
            {"row": 2, "column": "Rated power (W)", "code": "greater_than"}
        ]

    def test_rejects_unsupported_files(self, client: TestClient) -> None:
        response = client.post("/api/load-table/import", files={"file": ("notes.txt", b"hi")})

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "unsupported_file_type"

    def test_lists_missing_columns(self, client: TestClient) -> None:
        response = client.post(
            "/api/load-table/import", files={"file": ("x.csv", "Load,0\nLamp,1\n")}
        )

        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "missing_columns"
        assert "Rated power (W)" in response.json()["detail"]["columns"]

    def test_rejects_files_over_one_megabyte(self, client: TestClient) -> None:
        response = client.post(
            "/api/load-table/import", files={"file": ("big.csv", b"x" * 1_000_001)}
        )

        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "file_too_large"


class TestDownloads:
    @pytest.mark.parametrize("fmt", ["csv", "xlsx"])
    def test_export_returns_a_file_that_reads_back(self, client: TestClient, fmt: str) -> None:
        response = client.post("/api/load-table/export", params={"format": fmt}, json=SAMPLE_JSON)

        assert response.status_code == 200
        assert response.headers["content-disposition"] == (
            f'attachment; filename="load-table.{fmt}"'
        )
        assert len(read_load_table(response.content, f"x.{fmt}").loads) == 10

    def test_template_defaults_to_xlsx(self, client: TestClient) -> None:
        response = client.get("/api/load-table/template")

        assert response.headers["content-type"] == XLSX_TYPE
        assert "load-table-template.xlsx" in response.headers["content-disposition"]

    def test_unknown_format_is_rejected(self, client: TestClient) -> None:
        response = client.get("/api/load-table/template", params={"format": "pdf"})

        assert response.status_code == 422
        assert response.json()["detail"][0]["type"] == "literal_error"
