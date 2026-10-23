"""A misconfigured kuzu_role must stop the process, not fall through to
"owner" and quietly open the Kuzu file from a second process."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from archivum.config import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("KUZU_ROLE", "GRAPH_RPC_URL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("role", ["Client", "CLIENT", " client", "client ", "bogus", ""])
def test_unknown_role_is_refused(role):
    with pytest.raises(ValidationError):
        Settings(kuzu_role=role, graph_rpc_url="http://backend:8000")


@pytest.mark.parametrize("role", ["Client", "bogus"])
def test_unknown_role_from_env_is_refused(monkeypatch, role):
    monkeypatch.setenv("KUZU_ROLE", role)
    monkeypatch.setenv("GRAPH_RPC_URL", "http://backend:8000")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("url", ["", "   "])
def test_client_without_an_owner_url_is_refused(url):
    with pytest.raises(ValidationError, match="graph_rpc_url"):
        Settings(kuzu_role="client", graph_rpc_url=url)


def test_client_without_an_owner_url_from_env_is_refused(monkeypatch):
    monkeypatch.setenv("KUZU_ROLE", "client")
    with pytest.raises(ValidationError, match="graph_rpc_url"):
        Settings()


def test_valid_roles_construct():
    assert Settings().kuzu_role == "owner"
    assert Settings(kuzu_role="owner").kuzu_role == "owner"
    client = Settings(kuzu_role="client", graph_rpc_url="http://backend:8000")
    assert client.kuzu_role == "client"
