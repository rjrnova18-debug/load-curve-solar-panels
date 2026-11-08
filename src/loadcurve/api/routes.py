"""HTTP routes under the /api prefix."""

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the service is up; used by tests, CI and the hosting platform."""
    return {"status": "ok"}
