"""MCP Demo — standalone demo of Archivum's MCP interface using mock data.

One-command demo:  python -m archivum.mcp.demo
Writes inspectable artifacts to mcp-demo-out/ in the repo root.
No infrastructure (DB, Qdrant, Kuzu) required.

Usage:
    python -m archivum.mcp.demo                # run demo, write to default output dir
    python -m archivum.mcp.demo --output-dir /tmp/mcp-demo  # custom output dir
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Mock data ─────────────────────────────────────────────────────────────────

MOCK_PAGES: list[dict[str, Any]] = [
    {
        "slug": "getting-started",
        "title": "Getting Started with Archivum",
        "content": (
            "Archivum is a self-hosted knowledge base that ingests files and URLs, "
            "extracts structured notes via LLMs, and surfaces everything through a wiki. "
            "See [[mcp-setup]] and [[ingestion-guide]] for next steps."
        ),
        "tags": ["archivum", "getting-started"],
        "created_at": "2026-06-01T10:00:00Z",
        "updated_at": "2026-06-10T14:00:00Z",
        "authored_by": "owner",
    },
    {
        "slug": "mcp-setup",
        "title": "MCP Setup Guide",
        "content": (
            "# MCP Setup\n\n"
            "The Model Context Protocol (MCP) allows AI assistants to interact with Archivum directly.\n\n"
            "## SSE Transport\n"
            "Point your MCP client at `http://localhost:8001/sse`.\n\n"
            "## stdio Transport\n"
            "Run `python -m archivum.mcp.server --stdio`.\n\n"
            "## Available Tools\n\n"
            "- `ingest_source` — ingest files or URLs\n"
            "- `search_wiki` — semantic search\n"
            "- `list_pages` — list all pages\n"
            "- `get_page` — retrieve page content\n"
            "- `write_page` — create or update pages\n"
            "- `query` — ask questions with citations\n"
            "- `graph_neighbors` — explore knowledge graph\n"
            "- `lint_wiki` — health check\n\n"
            "See [[graph-export]] for visualisation and [[Archivum]] for architecture."
        ),
        "tags": ["mcp", "setup", "guide"],
        "created_at": "2026-06-02T09:00:00Z",
        "updated_at": "2026-06-08T11:00:00Z",
        "authored_by": "owner",
    },
    {
        "slug": "ingestion-guide",
        "title": "Ingestion Guide",
        "content": (
            "# Ingestion Guide\n\n"
            "Archivum supports many formats including PDF, DOCX, Markdown, HTML, "
            "JSON, code files, subtitles, email, and more.\n\n"
            "## How to ingest\n"
            "Use the ingest panel in the UI or the MCP `ingest_source` tool.\n\n"
            "## Related\n"
            "See [[mcp-setup]] for MCP-based ingestion and [[getting-started]] for the basics."
        ),
        "tags": ["ingest", "guide"],
        "created_at": "2026-06-03T08:00:00Z",
        "updated_at": "2026-06-09T16:00:00Z",
        "authored_by": "writer",
    },
    {
        "slug": "graph-export",
        "title": "Graph Export",
        "content": (
            "# Graph Export\n\n"
            "Archivum can export the knowledge graph as JSON and self-contained HTML.\n\n"
            "## Demo mode\n"
            "`python -m archivum.scripts.graph_export --demo`\n\n"
            "The graph is powered by Kuzu, an embedded graph database.\n"
            "See [[Kuzu]] for details and [[Archivum]] for how everything fits together."
        ),
        "tags": ["graph", "export", "visualisation"],
        "created_at": "2026-06-04T12:00:00Z",
        "updated_at": "2026-06-12T09:00:00Z",
        "authored_by": "owner",
    },
]

MOCK_SEARCH_RESULTS: list[dict[str, Any]] = [
    {"slug": "mcp-setup", "title": "MCP Setup Guide", "score": 0.92, "excerpt": "The Model Context Protocol (MCP) allows AI assistants to interact with Archivum directly."},
    {"slug": "getting-started", "title": "Getting Started with Archivum", "score": 0.78, "excerpt": "Archivum is a self-hosted knowledge base that ingests files and URLs."},
    {"slug": "graph-export", "title": "Graph Export", "score": 0.45, "excerpt": "Archivum can export the knowledge graph as JSON and self-contained HTML."},
]

MOCK_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "getting-started", "label": "Getting Started", "type": "page"},
        {"id": "mcp-setup", "label": "MCP Setup", "type": "page"},
        {"id": "ingestion-guide", "label": "Ingestion Guide", "type": "page"},
        {"id": "graph-export", "label": "Graph Export", "type": "page"},
        {"id": "Archivum", "label": "Archivum", "type": "entity", "entity_type": "wiki"},
        {"id": "Kuzu", "label": "Kuzu", "type": "entity", "entity_type": "db"},
    ],
    "edges": [
        {"from": "getting-started", "to": "mcp-setup", "type": "references"},
        {"from": "getting-started", "to": "ingestion-guide", "type": "references"},
        {"from": "mcp-setup", "to": "graph-export", "type": "references"},
        {"from": "mcp-setup", "to": "Archivum", "type": "mentions"},
        {"from": "ingestion-guide", "to": "mcp-setup", "type": "references"},
        {"from": "graph-export", "to": "Kuzu", "type": "mentions"},
        {"from": "graph-export", "to": "Archivum", "type": "mentions"},
        {"from": "Archivum", "to": "Kuzu", "type": "related_to"},
    ],
}


# ── Demo logic ────────────────────────────────────────────────────────────────


def _repo_root() -> Path:
    # apps/backend/archivum/mcp/demo.py -> repo root is parents[4]
    return Path(__file__).resolve().parents[4]


def default_output_dir() -> Path:
    return _repo_root() / "mcp-demo-out"


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _render_html_report(demo_steps: list[dict[str, Any]]) -> str:
    """Generate a self-contained HTML report summarizing all demo steps."""
    steps_html = ""
    for step in demo_steps:
        step_num = step.get("step", "")
        title = step.get("title", "")
        ok = step.get("ok", False)
        status_class = "ok" if ok else "err"
        status_text = "✅ OK" if ok else "❌ Failed"
        detail_json = json.dumps(step.get("data", {}), indent=2, ensure_ascii=False)
        output_files = step.get("output_files", [])

        output_html = ""
        if output_files:
            output_html += "<div class=\"output-files\">📁 Output files:<ul>"
            for f in output_files:
                output_html += f"<li><code>{f}</code></li>"
            output_html += "</ul></div>"

        steps_html += f"""
    <div class=\"step {status_class}\">
      <h3>Step {step_num}: {title} <span class=\"status\">{status_text}</span></h3>
      <pre><code>{detail_json}</code></pre>
      {output_html}
    </div>"""

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\"/>
  <meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>
  <title>Archivum MCP Demo Report</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; max-width: 960px; margin: 0 auto; padding: 24px 16px; background: #0d1117; color: #c9d1d9; }}
    h1 {{ color: #e6edf3; border-bottom: 1px solid #30363d; padding-bottom: 12px; }}
    h2 {{ color: #e6edf3; }}
    .step {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin: 12px 0; }}
    .step.ok {{ border-left: 4px solid #3fb950; }}
    .step.err {{ border-left: 4px solid #f85149; }}
    .step h3 {{ margin: 0 0 8px; }}
    .status {{ font-size: 14px; }}
    .ok .status {{ color: #3fb950; }}
    .err .status {{ color: #f85149; }}
    pre {{ background: #0d1117; border: 1px solid #30363d; border-radius: 6px; padding: 12px; overflow-x: auto; font-size: 13px; }}
    code {{ font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace; }}
    .output-files {{ margin-top: 8px; font-size: 14px; color: #8b949e; }}
    .output-files ul {{ margin: 4px 0 0; padding-left: 20px; }}
    .metadata {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 12px; margin-bottom: 20px; font-size: 14px; }}
    .cmd {{ margin: 20px 0; padding: 12px; background: #161b22; border: 1px solid #30363d; border-radius: 8px; font-size: 14px; }}
  </style>
</head>
<body>
  <h1>🦞 Archivum MCP Demo</h1>
  <div class=\"metadata\">
    <div><strong>Generated:</strong> {datetime.now(timezone.utc).isoformat()}</div>
    <div><strong>Mode:</strong> mock data / demo (no infrastructure required)</div>
  </div>
  {steps_html}
  <div class=\"cmd\">
    <strong>Try the real MCP server:</strong><br/>
    <code>python -m archivum.mcp.server --stdio</code> or <code>--sse</code>
  </div>
</body>
</html>
"""


def _graph_render_html(graph_json: str, title: str) -> str:
    """Render a self-contained SVG-based HTML page from graph JSON (no CDN)."""
    # Inline the same SVG renderer used by graph_export.py for self-containment
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <style>
      html, body {{ height: 100%; margin: 0; }}
      #canvas {{ width: 100%; height: calc(100% - 48px); display: block; background: #0b1220; }}
      .topbar {{ height: 48px; display: flex; align-items: center; gap: 12px; padding: 0 14px; background: #0b1220; color: #e6edf3; font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; }}
      .pill {{ background: rgba(255,255,255,0.12); padding: 6px 10px; border-radius: 999px; font-size: 12px; }}
      .node-label {{ font: 12px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; fill: #e6edf3; pointer-events: none; }}
      .edge-label {{ font: 10px system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; fill: rgba(230,237,243,0.85); pointer-events: none; }}
    </style>
  </head>
  <body>
    <div class="topbar"><div style="font-weight: 700;">{title}</div><div class="pill" id="meta"></div></div>
    <svg id="canvas" viewBox="0 0 1000 600" xmlns="http://www.w3.org/2000/svg" aria-label="Graph" role="img"></svg>
    <script>
      const graphData = {graph_json};
      const svg = document.getElementById('canvas');
      const NS = 'http://www.w3.org/2000/svg';
      function el(name, attrs) {{
        const e = document.createElementNS(NS, name);
        if (attrs) for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
        return e;
      }}
      function nodeColor(type) {{
        if (type === 'page') return '#1f77b4';
        if (type === 'entity') return '#ff7f0e';
        return '#7f7f7f';
      }}
      const nodes = graphData.nodes ?? [];
      const edges = graphData.edges ?? [];
      document.getElementById('meta').textContent = `${{nodes.length}} nodes u2022 ${{edges.length}} edges`;
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      const defs = el('defs');
      const marker = el('marker', {{ id: 'arrow', viewBox: '0 0 10 10', refX: '8', refY: '5', markerWidth: '8', markerHeight: '8', orient: 'auto-start-reverse' }});
      marker.appendChild(el('path', {{ d: 'M 0 0 L 10 5 L 0 10 z', fill: 'rgba(230,237,243,0.8)' }}));
      defs.appendChild(marker);
      svg.appendChild(defs);
      const cx = 500, cy = 300;
      const r = Math.min(240, 0.45 * Math.max(1, Math.sqrt(nodes.length)) * 240);
      const pos = new Map();
      nodes.forEach((n, i) => {{
        const angle = (Math.PI * 2 * i) / Math.max(1, nodes.length);
        pos.set(n.id, {{ x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), n }});
      }});
      edges.forEach(e => {{
        const a = pos.get(e.from), b = pos.get(e.to);
        if (!a || !b) return;
        svg.appendChild(el('line', {{ x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: 'rgba(230,237,243,0.35)', 'stroke-width': 2, 'marker-end': 'url(#arrow)' }}));
        const labelText = e.label ?? e.type ?? '';
        if (labelText) {{
          const text = el('text', {{ x: (a.x+b.x)/2, y: (a.y+b.y)/2, 'text-anchor': 'middle', 'dominant-baseline': 'central', class: 'edge-label' }});
          text.textContent = labelText;
          svg.appendChild(text);
        }}
      }});
      nodes.forEach(n => {{
        const p = pos.get(n.id);
        if (!p) return;
        svg.appendChild(el('circle', {{ cx: p.x, cy: p.y, r: 22, fill: nodeColor(n.type), stroke: 'rgba(0,0,0,0.25)', 'stroke-width': 2 }}));
        const text = el('text', {{ x: p.x, y: p.y+4, 'text-anchor': 'middle', class: 'node-label' }});
        text.textContent = (n.label ?? n.id);
        svg.appendChild(text);
      }});
    </script>
  </body>
</html>"""


def run_demo(output_dir: Path) -> dict[str, Any]:
    """Run the MCP demo against mock data. Returns a summary dict."""
    output_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    all_ok = True

    def record(step_num: int, title: str, ok: bool, data: Any, output_files: list[str] | None = None) -> None:
        steps.append({"step": step_num, "title": title, "ok": ok, "data": data, "output_files": output_files or []})
        nonlocal all_ok
        if not ok:
            all_ok = False

    # ── Step 1: list_pages ──────────────────────────────────────────────────
    pages_file = output_dir / "pages.json"
    _write_json(pages_file, MOCK_PAGES)
    record(
        1,
        "list_pages — list all wiki pages",
        True,
        {"count": len(MOCK_PAGES), "pages": [p["slug"] for p in MOCK_PAGES]},
        ["pages.json"],
    )

    # ── Step 2: get_page ────────────────────────────────────────────────────
    page = next(p for p in MOCK_PAGES if p["slug"] == "mcp-setup")
    page_file = output_dir / "page_mcp-setup.json"
    _write_json(page_file, page)
    record(
        2,
        "get_page — retrieve full page content by slug",
        True,
        {"slug": page["slug"], "title": page["title"], "content_length": len(page["content"]), "tags": page["tags"]},
        ["page_mcp-setup.json"],
    )

    # ── Step 3: search_wiki ─────────────────────────────────────────────────
    search_file = output_dir / "search_results.json"
    _write_json(search_file, MOCK_SEARCH_RESULTS)
    record(
        3,
        "search_wiki — semantic search",
        True,
        {"query": "MCP", "hits": len(MOCK_SEARCH_RESULTS), "top_result": MOCK_SEARCH_RESULTS[0]["title"]},
        ["search_results.json"],
    )

    # ── Step 4: write_page ──────────────────────────────────────────────────
    new_page = {
        "slug": "demo-created-page",
        "title": "Demo Created Page",
        "content": "This page was created during the MCP demo.\n\nIt references [[mcp-setup]] and [[graph-export]].",
        "tags": ["demo", "mcp"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "authored_by": "agent",
    }
    write_file = output_dir / "page_write_result.json"
    _write_json(write_file, new_page)
    record(
        4,
        "write_page — create or update a wiki page",
        True,
        {"action": "created", "slug": "demo-created-page", "title": new_page["title"]},
        ["page_write_result.json"],
    )

    # ── Step 5: ingest_source ───────────────────────────────────────────────
    ingest_result: dict[str, Any] = {
        "source": "mock://demo-file.md",
        "type": "created",
        "pages": ["demo-ingested-page"],
        "events": [
            {"stage": "parse", "status": "ok", "chars": 142},
            {"stage": "extract_entities", "status": "ok", "entities": 3},
            {"stage": "embed", "status": "ok", "chunks": 2},
            {"stage": "graph", "status": "ok", "edges_added": 4},
        ],
    }
    ingest_file = output_dir / "ingest_result.json"
    _write_json(ingest_file, ingest_result)
    record(
        5,
        "ingest_source — process a file or URL into the wiki",
        True,
        {"source": "mock://demo-file.md", "pages_created": 1, "pipeline_stages": 4},
        ["ingest_result.json"],
    )

    # ── Step 6: graph_neighbors ─────────────────────────────────────────────
    graph_file = output_dir / "graph_neighbors.json"
    _write_json(graph_file, MOCK_GRAPH)
    record(
        6,
        "graph_neighbors — query the knowledge graph",
        True,
        {"center": "mcp-setup", "nodes": len(MOCK_GRAPH["nodes"]), "edges": len(MOCK_GRAPH["edges"])},
        ["graph_neighbors.json"],
    )

    # ── Step 7: lint_wiki ───────────────────────────────────────────────────
    lint_data: dict[str, Any] = {
        "broken_wikilinks": [],
        "orphan_pages": [],
        "stats": {"total_pages": len(MOCK_PAGES) + 1, "healthy_links": 8, "broken_links": 0, "orphan_pages": 0},
    }
    lint_file = output_dir / "lint_result.json"
    _write_json(lint_file, lint_data)
    record(
        7,
        "lint_wiki — health check for broken wikilinks and orphans",
        True,
        lint_data["stats"],
        ["lint_result.json"],
    )

    # ── Step 8: query ───────────────────────────────────────────────────────
    query_data: dict[str, Any] = {
        "question": "How do I set up MCP in Archivum?",
        "answer": (
            "To set up MCP in Archivum, point your MCP client at `http://localhost:8001/sse` "
            "for SSE transport, or run `python -m archivum.mcp.server --stdio` for stdio transport. "
            "Both methods allow AI assistants to use Archivum tools including ingest_source, "
            "search_wiki, list_pages, get_page, write_page, query, graph_neighbors, and lint_wiki."
        ),
        "citations": [
            {"slug": "mcp-setup", "title": "MCP Setup Guide"},
            {"slug": "getting-started", "title": "Getting Started with Archivum"},
        ],
    }
    query_file = output_dir / "query_result.json"
    _write_json(query_file, query_data)
    record(
        8,
        "query — ask a question with cited sources",
        True,
        {"question": query_data["question"], "answer_length": len(query_data["answer"]), "citations": len(query_data["citations"])},
        ["query_result.json"],
    )

    # ── Step 9: graph export (self-contained, no imports needed) ───────────
    graph_out_dir = output_dir / "graph-export"
    graph_out_dir.mkdir(parents=True, exist_ok=True)

    # Normalize edges for frontend compatibility
    normalized_graph: dict[str, Any] = {
        "nodes": MOCK_GRAPH["nodes"],
        "edges": [
            {**e, "label": e.get("type", e.get("label", ""))}
            for e in MOCK_GRAPH["edges"]
        ],
    }
    (graph_out_dir / "graph.json").write_text(
        json.dumps(normalized_graph, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    html = _graph_render_html(json.dumps(normalized_graph, ensure_ascii=False), "Archivum MCP Demo Graph")
    (graph_out_dir / "graph.html").write_text(html, encoding="utf-8")

    export_manifest = {
        "mode": "demo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_files": ["graph.json", "graph.html", "manifest.json"],
        "notes": [
            "Generated from MOCK_GRAPH during MCP demo.",
            "Self-contained HTML with inline SVG — works offline, no CDN required.",
        ],
    }
    (graph_out_dir / "manifest.json").write_text(
        json.dumps(export_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    record(
        9,
        "export_graph_demo — generate offline graph visualisation",
        True,
        {
            "output_dir": str(graph_out_dir),
            "nodes": len(MOCK_GRAPH["nodes"]),
            "edges": len(MOCK_GRAPH["edges"]),
            "files": ["graph.json", "graph.html", "manifest.json"],
        },
        ["graph-export/graph.json", "graph-export/graph.html", "graph-export/manifest.json"],
    )

    # ── Write master report ─────────────────────────────────────────────────
    report_path = output_dir / "report.html"
    report_html = _render_html_report(steps)
    report_path.write_text(report_html, encoding="utf-8")

    manifest = {
        "demo": "Archivum MCP Demo",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "mock-data",
        "total_steps": len(steps),
        "all_passed": all_ok,
        "output_dir": str(output_dir),
        "steps": [{"num": s["step"], "title": s["title"], "ok": s["ok"]} for s in steps],
    }
    _write_json(output_dir / "manifest.json", manifest)

    output_files = [
        "manifest.json", "report.html", "pages.json",
        "page_mcp-setup.json", "search_results.json",
        "page_write_result.json", "ingest_result.json",
        "graph_neighbors.json", "lint_result.json", "query_result.json",
    ]
    if (output_dir / "graph-export").exists():
        output_files.extend(["graph-export/graph.json", "graph-export/graph.html", "graph-export/manifest.json"])

    return {
        "ok": all_ok,
        "output_dir": str(output_dir),
        "total_steps": len(steps),
        "output_files": output_files,
    }


def main() -> None:
    parser = argparse.ArgumentParser(prog="archivum-mcp-demo", description="Archivum MCP Demo — exercise all MCP tools with mock data.")
    parser.add_argument(
        "--output-dir",
        default=str(default_output_dir()),
        help=f"Where to write demo artifacts (default: {default_output_dir()})",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print(f"🧪 Archivum MCP Demo")
    print(f"   Output dir: {output_dir}")
    print(f"   Mode: mock data (no infrastructure required)")
    print()

    result = run_demo(output_dir)

    print(f"\n📄 Report: {output_dir / 'report.html'}")
    print(f"📊 All {result['total_steps']} steps complete — artifacts in {output_dir}/")

    if not result["ok"]:
        print("⚠️  Some steps had issues (non-critical for demo).")
        # Don't fail - the demo is still valuable even if one step has issues


if __name__ == "__main__":
    main()
