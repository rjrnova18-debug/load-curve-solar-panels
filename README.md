# Load Curve & Solar Sizing

A web tool to estimate the electrical consumption of a home, business or building from its load schedule, and to help decide how to size a solar PV system.

> 🚧 **Work in progress.** This is a full rewrite of my earlier Streamlit prototype, [Herramienta-Cuadro-de-Carga](https://github.com/rjrnova18-debug/Herramienta-Cuadro-de-Carga), using FastAPI, a tested calculation engine, and a redesigned frontend.

## Run locally

Requires Python 3.12.

```bash
python -m venv venv
source venv/Scripts/activate      # Windows (Git Bash); on macOS/Linux: source venv/bin/activate
pip install -e ".[dev]"

uvicorn loadcurve.api.app:app --reload
```

Open <http://127.0.0.1:8000> for the app and <http://127.0.0.1:8000/docs> for the interactive API docs.

## Development

```bash
pytest                 # run the tests
ruff check .           # lint
ruff format .          # format
```

## Project structure

```
src/loadcurve/
├── api/        FastAPI app and routes
└── web/        static frontend
tests/          pytest suite
```
