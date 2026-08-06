from __future__ import annotations

import json
from pathlib import Path

from archivum.archgraph.mapper import CandidateArtifact, CandidateEntity, CandidateRelationship


def build_graph_dict(candidates: list) -> dict:
    """Build a graph dict from a flat list of candidates.

    Returns:
        {
            "nodes": [{"id","label","kind","scope","extraction_method","confidence","citation"}],
            "edges": [{"source","target","relation","extraction_method","confidence"}],
        }

    Nodes sorted by id; edges sorted by (source, relation, target).
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    for c in candidates:
        if isinstance(c, (CandidateEntity, CandidateArtifact)):
            citation = c.provenance[0].chunk_id if c.provenance else ""
            nodes.append(
                {
                    "id": c.id,
                    "label": c.name,
                    "kind": c.kind,
                    "scope": c.scope,
                    "extraction_method": c.extraction_method,
                    "confidence": c.confidence,
                    "citation": citation,
                }
            )
        elif isinstance(c, CandidateRelationship):
            edges.append(
                {
                    "source": c.src_id,
                    "target": c.dst_id,
                    "relation": c.rel_type,
                    "extraction_method": c.extraction_method,
                    "confidence": c.confidence,
                }
            )

    nodes.sort(key=lambda n: n["id"])
    edges.sort(key=lambda e: (e["source"], e["relation"], e["target"]))

    return {"nodes": nodes, "edges": edges}


def export_graph(candidates: list, out_dir: Path) -> tuple[Path, Path]:
    """Write graph.json and graph.html to out_dir.

    Creates out_dir if needed. Returns (json_path, html_path).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    graph = build_graph_dict(candidates)

    json_path = out_dir / "graph.json"
    json_path.write_text(json.dumps(graph, indent=2, sort_keys=True))

    html_path = out_dir / "graph.html"
    html_path.write_text(_render_html(graph))

    return json_path, html_path


def _render_html(graph: dict) -> str:
    """Return a self-contained HTML string embedding the graph via vis-network CDN."""
    graph_json = json.dumps(graph, indent=2, sort_keys=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Archgraph — Code Graph</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  body {{ margin: 0; font-family: sans-serif; background: #1a1a2e; color: #eee; }}
  #graph {{ width: 100vw; height: 100vh; }}
  #legend {{ position: fixed; top: 12px; left: 12px; background: rgba(0,0,0,.6);
             padding: 8px 12px; border-radius: 6px; font-size: 12px; line-height: 1.8; }}
</style>
</head>
<body>
<div id="legend">
  <b>Edge style</b><br>
  &#9644; EXTRACTED (solid)<br>
  &#9135; INFERRED (dashed)<br>
  <span style="color:#e74c3c">&#9644;</span> AMBIGUOUS (red)
</div>
<div id="graph"></div>
<script>
var GRAPH_DATA = {graph_json};

var nodes = new vis.DataSet(GRAPH_DATA.nodes.map(function(n) {{
  return {{
    id: n.id,
    label: n.label + "\\n(" + n.kind + ")",
    title: "scope: " + n.scope + "\\nmethod: " + n.extraction_method + "\\ncitation: " + n.citation,
    color: {{ background: "#2980b9", border: "#1a5276" }},
    font: {{ color: "#fff" }},
  }};
}}));

var edges = new vis.DataSet(GRAPH_DATA.edges.map(function(e) {{
  var color = "#888";
  var dashes = false;
  if (e.extraction_method === "INFERRED") {{
    dashes = true;
    color = "#f39c12";
  }} else if (e.extraction_method === "AMBIGUOUS") {{
    color = "#e74c3c";
  }}
  return {{
    from: e.source,
    to: e.target,
    label: e.relation,
    dashes: dashes,
    color: {{ color: color }},
    arrows: "to",
    title: "method: " + e.extraction_method + "\\nconfidence: " + e.confidence,
  }};
}}));

var container = document.getElementById("graph");
var network = new vis.Network(container, {{ nodes: nodes, edges: edges }}, {{
  layout: {{ improvedLayout: true }},
  physics: {{ stabilization: {{ iterations: 150 }} }},
  edges: {{ font: {{ size: 10, color: "#ccc" }}, smooth: {{ type: "curvedCW", roundness: 0.2 }} }},
}});
</script>
</body>
</html>
"""
