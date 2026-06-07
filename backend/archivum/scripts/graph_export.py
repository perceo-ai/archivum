from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEMO_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "index", "label": "Index", "type": "page"},
        {"id": "ai-notes", "label": "AI Notes", "type": "page"},
        {"id": "mcp-setup", "label": "MCP Setup", "type": "page"},
        {"id": "graph-export", "label": "Graph Export", "type": "page"},
        {"id": "Archivum", "label": "Archivum", "type": "entity", "entity_type": "wiki"},
        {"id": "Kuzu", "label": "Kuzu", "type": "entity", "entity_type": "db"},
    ],
    "edges": [
        {"from": "index", "to": "ai-notes", "type": "references"},
        {"from": "index", "to": "mcp-setup", "type": "references"},
        {"from": "ai-notes", "to": "graph-export", "type": "references"},
        {"from": "mcp-setup", "to": "Archivum", "type": "mentions"},
        {"from": "graph-export", "to": "Kuzu", "type": "mentions"},
        {"from": "Archivum", "to": "Kuzu", "type": "related_to"},
    ],
}


@dataclass(frozen=True)
class ExportManifest:
    mode: str
    generated_at: str
    output_files: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "generated_at": self.generated_at,
            "output_files": self.output_files,
            "notes": self.notes,
        }


def _repo_root() -> Path:
    # backend/archivum/scripts/graph_export.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def default_output_dir() -> Path:
    """Repo-owned location where demo exports are written."""
    return _repo_root() / "graph-export-out"


def export_demo(output_dir: Path) -> dict[str, Any]:
    """Generate a self-contained demo graph export (no DB required)."""
    notes = [
        "Generated from DEMO_GRAPH fixtures (no Kuzu DB required).",
        "Nodes/edges format matches Archivum frontend expectations: {nodes:[...], edges:[{from,to,label/type}]}",
    ]

    write_export(
        DEMO_GRAPH,
        output_dir=output_dir,
        mode="demo",
        notes=notes,
    )

    manifest_path = output_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None

    return {
        "mode": "demo",
        "output_dir": str(output_dir),
        "files_written": ["graph.json", "graph.html", "manifest.json"],
        "manifest": manifest,
        "notes": notes,
    }


def render_html(graph: dict[str, Any], title: str) -> str:
    graph_json = json.dumps(graph, ensure_ascii=False)

    template = """<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>__TITLE__</title>
    <style>
      html, body { height: 100%; margin: 0; }
      #network { width: 100%; height: calc(100% - 48px); }
      .topbar { height: 48px; display: flex; align-items: center; gap: 12px; padding: 0 14px; background: #0b1220; color: #e6edf3; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; }
      .pill { background: rgba(255,255,255,0.12); padding: 6px 10px; border-radius: 999px; font-size: 12px; }
    </style>
    <link href=\"https://unpkg.com/vis-network/styles/vis-network.min.css\" rel=\"stylesheet\" />
    <script src=\"https://unpkg.com/vis-network/standalone/umd/vis-network.min.js\"></script>
  </head>
  <body>
    <div class=\"topbar\">
      <div style=\"font-weight: 700;\">__TITLE__</div>
      <div class=\"pill\" id=\"meta\"></div>
    </div>
    <div id=\"network\"></div>

    <script>
      const graphData = __GRAPH_JSON__;

      const nodes = new vis.DataSet(graphData.nodes.map(n => {
        const bg = n.type === 'page' ? '#1f77b4'
          : (n.type === 'entity' ? '#ff7f0e' : '#7f7f7f');
        return {
          id: n.id,
          label: n.label ?? n.id,
          shape: 'dot',
          color: { background: bg, border: 'rgba(0,0,0,0.2)' },
          font: { color: '#111', size: 12 },
          type: n.type
        };
      }));

      const edges = new vis.DataSet(graphData.edges.map(e => ({
        from: e.from,
        to: e.to,
        label: e.type ?? '',
        arrows: 'to',
        font: { align: 'top', size: 10 },
        smooth: { enabled: true, type: 'dynamic' },
        color: { color: 'rgba(0,0,0,0.35)' }
      })));

      document.getElementById('meta').textContent = `${graphData.nodes.length} nodes • ${graphData.edges.length} edges`;

      const container = document.getElementById('network');
      const data = { nodes, edges };
      const options = {
        interaction: { hover: true },
        physics: { stabilization: false, barnesHut: { gravitationalConstant: -2000, springLength: 95 } },
        layout: { improvedLayout: true }
      };

      new vis.Network(container, data, options);
    </script>
  </body>
</html>
"""

    return template.replace("__TITLE__", title).replace("__GRAPH_JSON__", graph_json)


def write_export(graph: dict[str, Any], output_dir: Path, mode: str, notes: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "graph.json").write_text(
        json.dumps(graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    html = render_html(graph, title=f"Archivum graph export ({mode})")
    (output_dir / "graph.html").write_text(html, encoding="utf-8")

    manifest = ExportManifest(
        mode=mode,
        generated_at=datetime.now(timezone.utc).isoformat(),
        output_files=["graph.json", "graph.html", "manifest.json"],
        notes=notes,
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="archivum-graph-export")
    parser.add_argument("--demo", action="store_true", help="Use repo-owned mock graph data (no DB required).")
    parser.add_argument("--wiki-id", default="default", help="Wiki id when exporting from DB (non-demo mode).")
    parser.add_argument(
        "--output-dir",
        default=str(_repo_root() / "graph-export-out"),
        help="Where to write graph.json + graph.html.",
    )
    parser.add_argument(
        "--fallback-to-demo",
        action="store_true",
        help="If DB export fails (e.g., missing dependencies), fall back to demo data.",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)

    if args.demo:
        export_demo(output_dir=output_dir)
        print(f"OK: wrote {output_dir / 'graph.json'} and {output_dir / 'graph.html'}")
        return

    # Non-demo: try exporting from the live Kuzu graph.
    try:
        from archivum.db import graph as graph_db

        import asyncio

        graph_data = asyncio.run(graph_db.get_all_nodes_edges(wiki_id=args.wiki_id))
        write_export(
            graph_data,
            output_dir=output_dir,
            mode=f"db:{args.wiki_id}",
            notes=["Generated from Kuzu graph DB via archivum.db.graph.get_all_nodes_edges()."],
        )
        print(f"OK: wrote {output_dir / 'graph.json'} and {output_dir / 'graph.html'}")
        return

    except Exception as e:
        if not args.fallback_to_demo:
            raise SystemExit(
                "DB export failed. Re-run with --fallback-to-demo (or use --demo).\n"
                f"Error: {e}"
            )

        write_export(
            DEMO_GRAPH,
            output_dir=output_dir,
            mode="demo:fallback",
            notes=["DB export failed; fell back to DEMO_GRAPH fixtures.", f"DB error: {e}"],
        )
        print(f"WARN: DB export failed; wrote demo output to {output_dir}")


if __name__ == "__main__":
    main()
