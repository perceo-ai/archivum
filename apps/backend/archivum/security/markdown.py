from __future__ import annotations

import bleach


def sanitize_markdown(md: str | None) -> str:
    """Remove any embedded raw HTML from markdown.

    - Preserves fenced code blocks (``` ... ```).
    - Outside code blocks, strips HTML tags using bleach.
    """

    if md is None:
        return ""
    if not md:
        return md

    out: list[str] = []
    in_fence = False

    for line in md.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue

        if in_fence:
            out.append(line)
        else:
            # Treat the markdown as potential HTML and strip tags.
            out.append(bleach.clean(line, tags=[], attributes={}, strip=True))

    return "".join(out)

