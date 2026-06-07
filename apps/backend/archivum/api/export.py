"""Export routes: /api/export"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from archivum.auth import CurrentUser, get_current_user
from archivum.db import sqlite

router = APIRouter(prefix="/api/export", tags=["export"])
logger = logging.getLogger(__name__)

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Georgia, 'Times New Roman', serif;
    background: #fafafa;
    color: #1a1a1a;
    line-height: 1.7;
    padding: 3rem 1.5rem;
}
.prose {
    max-width: 720px;
    margin: 0 auto;
}
h1 { font-size: 2rem; font-weight: 700; margin-bottom: 1.5rem; border-bottom: 2px solid #e0e0e0; padding-bottom: 0.5rem; }
h2 { font-size: 1.5rem; font-weight: 600; margin: 2rem 0 0.75rem; }
h3 { font-size: 1.25rem; font-weight: 600; margin: 1.5rem 0 0.5rem; }
h4, h5, h6 { font-size: 1rem; font-weight: 600; margin: 1.25rem 0 0.4rem; }
p { margin: 0.75rem 0; }
a { color: #2563eb; text-decoration: underline; }
ul, ol { margin: 0.75rem 0 0.75rem 1.5rem; }
li { margin: 0.3rem 0; }
blockquote {
    border-left: 4px solid #d1d5db;
    padding-left: 1rem;
    color: #555;
    margin: 1rem 0;
    font-style: italic;
}
code {
    background: #f3f4f6;
    padding: 0.1em 0.35em;
    border-radius: 3px;
    font-family: 'Courier New', Courier, monospace;
    font-size: 0.9em;
}
pre {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    border-radius: 6px;
    padding: 1rem;
    overflow-x: auto;
    margin: 1rem 0;
}
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
th, td { border: 1px solid #d1d5db; padding: 0.5rem 0.75rem; text-align: left; }
th { background: #f3f4f6; font-weight: 600; }
hr { border: none; border-top: 1px solid #e0e0e0; margin: 2rem 0; }
img { max-width: 100%; height: auto; }
"""


def _build_html(title: str, content_md: str) -> str:
    import markdown as md_lib

    body_html = md_lib.markdown(
        content_md,
        extensions=["extra", "toc", "fenced_code", "tables"],
    )
    escaped_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<!DOCTYPE html>\n"
        f"<html lang=\"en\">\n"
        f"<head>\n"
        f"  <meta charset=\"UTF-8\" />\n"
        f"  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />\n"
        f"  <title>{escaped_title}</title>\n"
        f"  <style>{_CSS}</style>\n"
        f"</head>\n"
        f"<body>\n"
        f"  <div class=\"prose\">\n"
        f"    <h1>{escaped_title}</h1>\n"
        f"    {body_html}\n"
        f"  </div>\n"
        f"</body>\n"
        f"</html>"
    )


@router.get("")
async def export_page(
    slug: str = Query(..., description="Page slug"),
    format: str = Query("html", description="Export format: html or pdf"),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    row = await sqlite.get_page(slug, current_user.wiki_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )

    title: str = row["title"] or slug
    content: str = row["content"] or ""

    # Derive a safe filename from slug (replace path separators)
    safe_name = slug.replace("/", "__")

    if format == "html":
        html_str = _build_html(title, content)
        return Response(
            content=html_str.encode("utf-8"),
            media_type="text/html; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.html"'},
        )

    if format == "pdf":
        html_str = _build_html(title, content)
        try:
            from weasyprint import HTML as WeasyprintHTML  # type: ignore[import]
        except ImportError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={"detail": "PDF export requires WeasyPrint; not installed", "code": "pdf_unavailable"},
            ) from exc

        pdf_bytes: bytes = WeasyprintHTML(string=html_str).write_pdf()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"detail": f"Unknown format '{format}'. Use 'html' or 'pdf'.", "code": "invalid_format"},
    )
