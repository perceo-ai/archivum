"""The one-line install path: GET /install, /install.ps1, /install/cli.tar.gz."""

from __future__ import annotations

import gzip
import io
import tarfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from archivum.api.install import build_cli_tarball


@pytest.fixture
def install_client():
    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
    ):
        from archivum.main import create_app

        yield TestClient(create_app(), base_url="http://vault.example.com")


def test_the_installer_needs_no_authentication(install_client):
    """It is public code, and the credential comes from the environment.

    Requiring a key here would mean needing a key to fetch the tool whose job
    is obtaining a key.
    """
    assert install_client.get("/install").status_code == 200


def test_the_installer_carries_the_server_it_was_fetched_from(install_client):
    """Why no --host flag is ever needed: the URL is the server identity."""
    body = install_client.get("/install").text

    assert 'BASE="http://vault.example.com"' in body


def test_the_installer_links_when_a_provisioning_token_is_in_the_environment(install_client):
    body = install_client.get("/install").text

    assert "ARCHIVUM_PROVISION_TOKEN" in body
    assert "connect --auto" in body


def test_the_installer_explains_itself_when_no_token_is_set(install_client):
    """An installer that silently does half the job is worse than one that says so."""
    body = install_client.get("/install").text

    assert "not linked" in body
    assert "Settings" in body


def test_the_installer_refuses_an_unsupported_node(install_client):
    body = install_client.get("/install").text

    assert "node 20+ is required" in body


def test_a_powershell_installer_is_served_for_windows(install_client):
    body = install_client.get("/install.ps1").text

    assert "$Base = 'http://vault.example.com'" in body
    assert "connect --auto" in body


def test_the_tarball_contains_a_runnable_cli(install_client):
    response = install_client.get("/install/cli.tar.gz")

    assert response.status_code == 200
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
        names = tar.getnames()
    # The launcher the install script writes runs exactly this file.
    assert "src/index.js" in names
    assert "src/connect.js" in names
    assert "package.json" in names


def test_the_tarball_carries_only_source(install_client):
    """A stray file in the vendored directory must not reach a user's machine."""
    with tarfile.open(fileobj=io.BytesIO(build_cli_tarball()), mode="r:gz") as tar:
        names = tar.getnames()

    assert all(name.endswith((".js", ".json")) for name in names), names


def test_the_tarball_is_byte_identical_across_builds():
    """So a machine re-running the install line sees the same artifact.

    Two timestamps have to be pinned, not one: the tar members carry their own
    mtimes, and the gzip wrapper carries a separate one. Comparing two builds
    only catches the wrapper when they straddle a second boundary, which is why
    the wrapper's mtime is asserted directly instead — that fails on every run
    if the stream goes back to `tarfile.open(mode="w:gz")`.
    """
    first = build_cli_tarball()
    with patch("archivum.api.install.gzip.GzipFile", wraps=gzip.GzipFile) as spy:
        second = build_cli_tarball()

    assert first == second
    # The wrapper's mtime must be pinned explicitly; `tarfile.open(mode="w:gz")`
    # would write the current time and differ across a second boundary.
    assert spy.call_args.kwargs.get("mtime") == 0


def test_the_tarball_carries_the_commands_the_stack_needs(install_client):
    """index and watch are how B and C reach a machine the server cannot read."""
    import io
    import tarfile

    response = install_client.get("/install/cli.tar.gz")

    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
        names = tar.getnames()

    assert "src/index-repo.js" in names
    assert "src/watch.js" in names
