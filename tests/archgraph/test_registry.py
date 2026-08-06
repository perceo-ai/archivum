from __future__ import annotations

from archivum.archgraph.registry import (
    CODE_SUFFIXES,
    LANGUAGE_REGISTRY,
    _PYTHON_CONFIG,
    _TSX_CONFIG,
    config_for_suffix,
    load_parser,
)
from archivum.archgraph.extractors.base import _make_id


def test_python_suffix_maps():
    assert config_for_suffix(".py").name == "python"
    assert ".ts" in LANGUAGE_REGISTRY
    assert config_for_suffix(".rb") is None


def test_load_parser_parses():
    parser = load_parser(_PYTHON_CONFIG)
    tree = parser.parse(b"x = 1")
    assert tree.root_node.type == "module"
    assert not tree.root_node.has_error


def test_tsx_config_loads():
    cfg = config_for_suffix(".tsx")
    parser = load_parser(cfg)
    # just confirm it built without error
    assert parser is not None


def test_make_id_slugifies():
    assert _make_id("Foo/Bar", "baz.py") == "foo_bar_baz_py"
