from __future__ import annotations

import re
from typing import Any


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
BOOLEAN_CLAIM_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9 _/-]{1,80}?)\s+is\s+(enabled|disabled)\b",
    re.IGNORECASE,
)


def analyze_wiki_pages(pages: list[dict[str, Any]]) -> dict[str, Any]:
    slug_set = {p["slug"] for p in pages}

    inbound: dict[str, int] = {s: 0 for s in slug_set}
    outbound: dict[str, int] = {s: 0 for s in slug_set}
    broken: list[dict[str, Any]] = []
    claims: dict[str, dict[str, set[str]]] = {}

    for p in pages:
        slug = p["slug"]
        content = p.get("content", "") or ""

        for target in (t.strip() for t in WIKILINK_RE.findall(content)):
            if not target:
                continue
            outbound[slug] = outbound.get(slug, 0) + 1
            if target in slug_set:
                inbound[target] = inbound.get(target, 0) + 1
            else:
                broken.append(
                    {
                        "type": "broken_wikilink",
                        "page": slug,
                        "target": target,
                        "suggestion": f"Create page '{target}' or fix link.",
                    }
                )

        for match in BOOLEAN_CLAIM_RE.finditer(content):
            subject = " ".join(match.group(1).lower().split())
            claim = match.group(2).lower()
            claims.setdefault(subject, {}).setdefault(claim, set()).add(slug)

    orphan_pages = [
        {
            "type": "orphan_page",
            "page": s,
            "suggestion": "Add links to/from other pages so this page is discoverable.",
        }
        for s in slug_set
        if inbound.get(s, 0) == 0 and outbound.get(s, 0) == 0
    ]

    contradictory_claims = []
    for subject, by_claim in claims.items():
        if not {"enabled", "disabled"}.issubset(by_claim):
            continue
        pages_with_claims = sorted(by_claim["enabled"] | by_claim["disabled"])
        contradictory_claims.append(
            {
                "type": "contradictory_claim",
                "subject": subject,
                "pages": pages_with_claims,
                "claims": ["enabled", "disabled"],
                "suggestion": f"Resolve conflicting enabled/disabled statements about '{subject}'.",
            }
        )

    issues = broken + orphan_pages + contradictory_claims
    return {
        "issues": issues,
        "broken_wikilinks": broken,
        "orphan_pages": orphan_pages,
        "contradictory_claims": contradictory_claims,
    }
