"""FastAPI application: the JSON API plus the static frontend."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from loadcurve.api.routes import router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app() -> FastAPI:
    """Build a fresh application instance (tests create their own)."""
    app = FastAPI(
        title="Load Curve & Solar Sizing",
        version="0.1.0",
        description="Load profile analysis and solar PV system sizing.",
    )
    app.include_router(router)
    # Mounted last: "/" would otherwise shadow the /api routes.
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


app = create_app()
