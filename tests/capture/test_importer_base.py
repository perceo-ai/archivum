from pathlib import Path

from archivum.capture.importers import all_connectors, connector_for, register
from archivum.capture.importers.base import ImportResult


class _Fake:
    interface = "fake"

    def can_handle(self, path):
        return path.suffix == ".fake"

    def parse(self, path):
        return ImportResult(conversations=(), interface="fake")


def test_registry_dispatches_by_can_handle():
    register(_Fake())
    assert connector_for(Path("x.fake")).interface == "fake"
    assert connector_for(Path("x.nope")) is None
    assert any(c.interface == "fake" for c in all_connectors())
