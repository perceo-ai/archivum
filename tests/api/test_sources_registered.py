"""The sources router must be mounted on the app."""

from __future__ import annotations


def test_sources_ingest_route_exists(app_client):
    paths = {route.path for route in app_client.app.routes}
    assert "/api/sources/ingest" in paths
    assert "/api/sources/{source_id}" in paths
