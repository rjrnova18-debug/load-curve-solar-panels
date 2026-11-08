# Load Curve & Solar Sizing

A web tool to estimate the electrical consumption of a home, business or building from its load schedule, and to help decide how to size a solar PV system.

> 🚧 **Work in progress.** This is a full rewrite of my earlier Streamlit prototype, [Herramienta-Cuadro-de-Carga](https://github.com/rjrnova18-debug/Herramienta-Cuadro-de-Carga), using FastAPI, a tested calculation engine, and a redesigned frontend. The API is complete; the new interface is in progress.

## Features

- **Load table**: each piece of equipment with its rated power, a usage factor (a fridge compressor runs ~40% of the time) and the hours it is on. Import and export as CSV or Excel, including the legacy Spanish template.
- **Load analysis**: hourly profile, load duration curve, peak/base/mean power and load factor for the whole day, daytime and night-time, and a monthly and yearly projection with seasonal multipliers.
- **Solar resource**: monthly peak sun hours for any location, looked up from [PVGIS](https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis_en) (EU Joint Research Centre) or entered by hand.
- **System sizing**: on-grid, hybrid and off-grid systems compared side by side (array kWp, panels, battery kWh, inverter kW), using the peak-sun-hours method with editable assumptions.
- **Excel report** with every table, ready to keep working on.

## Run locally

Requires Python 3.12.

```bash
python -m venv venv
source venv/Scripts/activate      # Windows (Git Bash); on macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"

python -m loadcurve
```

Open <http://127.0.0.1:8000> for the app and <http://127.0.0.1:8000/docs> for the interactive API docs.

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/analysis` | Analyse a study; sizes the three system types when it has a solar resource |
| `GET` | `/api/solar-resource?lat=&lon=` | Monthly peak sun hours and optimal panel orientation from PVGIS |
| `POST` | `/api/load-table/import` | Read a CSV/XLSX load table; invalid rows are reported, not fatal |
| `POST` | `/api/load-table/export?format=csv\|xlsx` | Download a load table |
| `GET` | `/api/load-table/template?format=csv\|xlsx` | Download the sample load table |
| `POST` | `/api/report` | Download the study and its results as an Excel workbook |
| `GET` | `/api/health` | Health check |

Errors carry stable codes for the frontend to translate: validation errors use FastAPI's `422` body (`detail[].type`), everything else returns `{"detail": {"code": "..."}}` (for example `location_over_sea` or `missing_columns`).

## Development

```bash
pytest                 # run the tests
ruff check .           # lint
ruff format .          # format
```

## Project structure

```
src/loadcurve/
├── domain/     pure calculations: models, analysis, sizing, study
├── files/      CSV/XLSX import/export and the Excel report (pandas)
├── solar/      PVGIS adapter
├── api/        FastAPI app and routes
└── web/        static frontend
tests/          pytest suite, mirroring src/
```
