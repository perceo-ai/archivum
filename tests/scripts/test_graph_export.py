"""Tests for archivum.scripts.graph_export — graph export script and helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

# Load the script module from its location at backend/archivum/scripts/graph_export.py
_script_path = Path(__file__).resolve().parents[2] / "backend" / "archivum" / "scripts" / "graph_export.py"
_spec = importlib.util.spec_from_file_location("archivum.scripts.graph_export", _script_path)
assert _spec is not None
_graph_export = importlib.util.module_from_spec(_spec)
sys.modules["archivum.scripts.graph_export"] = _graph_export
sys.modules["archivum.scripts"] = type(sys)("archivum.scripts")  # dummy parent
sys.modules["archivum"] = type(sys)("archivum")  # dummy grandparent
_spec.loader.exec_module(_graph_export)  # type: ignore[attr-defined]

DEMO_GRAPH = _graph_export.DEMO_GRAPH
ExportManifest = _graph_export.ExportManifest
_normalize_edges = _graph_export._normalize_edges
export_demo = _graph_export.export_demo
render_html = _graph_export.render_html
write_export = _graph_export.write_export


# ── DEMO_GRAPH ────────────────────────────────────────────────────────────────


class TestDemoGraph:
    def test_has_nodes_and_edges_keys(self):
        assert "nodes" in DEMO_GRAPH
        assert "edges" in DEMO_GRAPH

    def test_nodes_have_id_and_label(self):
        for node in DEMO_GRAPH["nodes"]:
            assert "id" in node
            assert "label" in node

    def test_edges_have_from_to_type(self):
        for edge in DEMO_GRAPH["edges"]:
            assert "from" in edge
            assert "to" in edge
            # type may be absent if only label is present, but DEMO_GRAPH uses type
            assert "type" in edge or "label" in edge

    def test_all_edges_reference_valid_nodes(self):
        node_ids = {n["id"] for n in DEMO_GRAPH["nodes"]}
        for edge in DEMO_GRAPH["edges"]:
            assert edge["from"] in node_ids, f"edge from '{edge['from']}' not in nodes"
            assert edge["to"] in node_ids, f"edge to '{edge['to']}' not in nodes"

    def test_non_empty(self):
        assert len(DEMO_GRAPH["nodes"]) > 0
        assert len(DEMO_GRAPH["edges"]) > 0


# ── ExportManifest ────────────────────────────────────────────────────────────


class TestExportManifest:
    def test_to_dict_includes_all_fields(self):
        m = ExportManifest(
            mode="demo",
            generated_at="2026-01-01T00:00:00+00:00",
            output_files=["graph.json", "graph.html", "manifest.json"],
            notes=["Test note."],
        )
        d = m.to_dict()
        assert d["mode"] == "demo"
        assert d["generated_at"] == "2026-01-01T00:00:00+00:00"
        assert d["output_files"] == ["graph.json", "graph.html", "manifest.json"]
        assert d["notes"] == ["Test note."]

    def test_dataclass_is_frozen(self):
        m = ExportManifest(
            mode="demo",
            generated_at="now",
            output_files=["f.json"],
            notes=["n"],
        )
        with pytest.raises(Exception):
            m.mode = "db"  # type: ignore[misc]


# ── _normalize_edges ──────────────────────────────────────────────────────────


class TestNormalizeEdges:
    def test_preserves_existing_label(self):
        graph = {
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [{"from": "a", "to": "b", "label": "custom"}],
        }
        result = _normalize_edges(graph)
        assert result["edges"][0]["label"] == "custom"
        assert "type" not in result["edges"][0]

    def test_maps_type_to_label_when_label_missing(self):
        graph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"from": "a", "to": "b", "type": "REFERENCES"}],
        }
        result = _normalize_edges(graph)
        assert result["edges"][0]["label"] == "REFERENCES"
        assert result["edges"][0]["type"] == "REFERENCES"

    def test_uses_empty_label_when_both_missing(self):
        graph = {
            "nodes": [{"id": "a"}, {"id": "b"}],
            "edges": [{"from": "a", "to": "b"}],
        }
        result = _normalize_edges(graph)
        assert result["edges"][0]["label"] == ""

    def test_skips_non_dict_edges(self):
        graph = {
            "nodes": [],
            "edges": [{"from": "a", "to": "b", "type": "ref"}, "not-a-dict"],
        }
        result = _normalize_edges(graph)
        assert len(result["edges"]) == 1

    def test_preserves_nodes(self):
        graph = {
            "nodes": [{"id": "x", "label": "X"}],
            "edges": [],
        }
        result = _normalize_edges(graph)
        assert result["nodes"] == graph["nodes"]


# ── render_html ───────────────────────────────────────────────────────────────


class TestRenderHtml:
    def test_returns_html_string(self):
        html = render_html(DEMO_GRAPH, title="Test Graph")
        assert "<!doctype html>" in html.lower()
        assert "<title>Test Graph</title>" in html

    def test_embeds_graph_json(self):
        html = render_html(DEMO_GRAPH, title="Test")
        # The graph JSON should be embedded as a JS variable
        assert "const graphData = " in html
        # Spot-check a node id from the embedded JSON
        assert '"id"' in html
        assert '"index"' in html

    def test_contains_svg_canvas(self):
        html = render_html(DEMO_GRAPH, title="T")
        assert '<svg id="canvas"' in html

    def test_contains_node_count_in_meta(self):
        html = render_html(DEMO_GRAPH, title="T")
        # The JS code sets meta textContent with a template literal for node/edge counts
        assert "nodes.length" in html
        assert "edges.length" in html
        assert 'getElementById(' in html


# ── write_export ──────────────────────────────────────────────────────────────


class TestWriteExport:
    def test_creates_output_files(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            write_export(DEMO_GRAPH, output_dir=out, mode="test", notes=["test note"])

            assert (out / "graph.json").exists()
            assert (out / "graph.html").exists()
            assert (out / "manifest.json").exists()

    def test_graph_json_is_valid_and_has_label(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            write_export(DEMO_GRAPH, output_dir=out, mode="test", notes=["n"])

            data = json.loads((out / "graph.json").read_text(encoding="utf-8"))
            assert "nodes" in data
            assert "edges" in data
            # All edges should have a label after normalization
            for edge in data["edges"]:
                assert "label" in edge

    def test_manifest_has_correct_fields(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            write_export(DEMO_GRAPH, output_dir=out, mode="test", notes=["n1", "n2"])

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["mode"] == "test"
            assert "generated_at" in manifest
            assert "output_files" in manifest
            assert manifest["notes"] == ["n1", "n2"]

    def test_creates_output_dir_if_missing(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "nested" / "subdir"
            write_export(DEMO_GRAPH, output_dir=out, mode="demo", notes=["n"])
            assert out.exists()
            assert (out / "graph.json").exists()


# ── export_demo ───────────────────────────────────────────────────────────────


class TestExportDemo:
    def test_returns_expected_structure(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            result = export_demo(output_dir=out)

            assert result["mode"] == "demo"
            assert result["output_dir"] == str(out)
            assert "graph.json" in result["files_written"]
            assert "graph.html" in result["files_written"]
            assert "manifest.json" in result["files_written"]
            assert isinstance(result["notes"], list)

    def test_writes_files_to_disk(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            result = export_demo(output_dir=out)

            for fname in result["files_written"]:
                assert (out / fname).exists(), f"Expected {fname} to exist"

    def test_graph_json_is_parseable(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            export_demo(output_dir=out)

            data = json.loads((out / "graph.json").read_text(encoding="utf-8"))
            assert "nodes" in data
            assert "edges" in data
            assert len(data["nodes"]) == len(DEMO_GRAPH["nodes"])

    def test_html_is_self_contained_no_cdn(self):
        """The demo HTML should be self-contained — no CDN scripts or external assets."""
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            export_demo(output_dir=out)

            html = (out / "graph.html").read_text(encoding="utf-8")
            # Must not reference any external CDN
            assert "cdn" not in html.lower()
            # Must not load external scripts
            assert 'src="http' not in html

    def test_manifest_records_demo_mode(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            export_demo(output_dir=out)

            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["mode"] == "demo"


# ── Integration: simulate the CLI --demo invocation ───────────────────────────


class TestCliDemoInvocation:
    """Verify the script can be imported and invoked programmatically (no subprocess)."""

    def test_main_demo_flag_writes_output(self):
        with TemporaryDirectory() as tmpdir:
            out = Path(tmpdir)
            # Simulate: python -m archivum.scripts.graph_export --demo --output-dir <tmpdir>
            with mock.patch(
                "sys.argv",
                [
                    "archivum.scripts.graph_export",
                    "--demo",
                    "--output-dir",
                    str(out),
                ],
            ):
                from archivum.scripts.graph_export import main

                main()

            assert (out / "graph.json").exists()
            assert (out / "graph.html").exists()
            assert (out / "manifest.json").exists()
