"""Shared resources injected into routes; tests replace them via ``app.dependency_overrides``."""

from collections.abc import Iterator

import httpx2


def get_http_client() -> Iterator[httpx2.Client]:
    """An HTTP client for outbound calls (PVGIS), closed when the request ends."""
    with httpx2.Client() as client:
        yield client
