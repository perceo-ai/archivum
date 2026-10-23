"""Turn a repository's code graph into pages you own.

Everything else in Archivum ends up as markdown in the vault. Code was the one
exception: it produced canonical records and a lexical index and no files at
all, which meant the only part of a developer's memory that could not be read,
edited, linked or exported was the part about their own work.

So the graph is written down the way a person would want to read it — one page
per community, plus an index — and then handed to the same `reindex_page` path
that every other write uses. From that moment the code graph is ordinary vault
content: backlinked, searchable, editable, and portable if Archivum goes away.

Communities come from the existing deterministic graph audit rather than a
model, so the same repository always produces the same clusters.

A list of members and edges is metadata about a cluster, not knowledge about
code: it cannot say what the subsystem is for. So each page leads with a short
narrative a model writes from the extracted signatures, docstrings and
locations, under the same two rules as `summaries.py`:

* **It cites what it was shown.** A narrative that names a line it was never
  given is rejected, however fluent it reads.
* **A failed model leaves nothing.** No narrative means no page — never a stub,
  because a stub outranks real content precisely by being short.

Narratives are keyed by a fingerprint of what they were written from, so an
unchanged cluster reuses its narrative: no model call and no churn.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from archivum.archgraph.registry import CODE_SUFFIXES
from archivum.config import Settings
from archivum.db import sqlite
from archivum.indexing import ensure_frontmatter, forget_page, reindex_page
from archivum.knowledge.graph_audit import (
    Community,
    GraphReport,
    audit_knowledge_graph,
)
from archivum.knowledge.models import KnowledgeObject
from archivum.knowledge.personal_root import SELF_ID
from archivum.knowledge.repository import KnowledgeRepository
from archivum.llm.cli_client import CliModelError, cli_chat_completion
from archivum.llm.prompt_context import with_context

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for type checkers
    from archivum.code_repos import CodeRepo

logger = logging.getLogger(__name__)

# A community with one member is a fact about that member, not a cluster worth
# its own page; it stays listed on the index instead.
MIN_COMMUNITY_SIZE = 2

# The repository node and its commit cluster together and describe nothing about
# the code. A page titled after the repository holding only "this repo, that
# commit" would compete with the index for the same name and the same reader.
_BOOKKEEPING_KINDS = frozenset({"repo", "commit"})

# Enough to show the shape of a cluster without pasting the repository into the
# vault. The canonical records remain the complete answer.
MAX_MEMBERS_PER_PAGE = 60
MAX_SURPRISING = 10

# What a model is shown per cluster: enough to characterise it, not the repo.
MAX_MEMBERS_IN_PROMPT = 40
MAX_NEIGHBOURS_IN_PROMPT = 8

# Below this, a "narrative" is a sentence about the cluster rather than an
# account of the code — exactly the stub this module must never write.
MIN_NARRATIVE_WORDS = 40

# Clusters are narrated largest first, a few at a time. The budget bounds what
# one indexing run can spend on a very large repository; a cluster past it is
# listed on the index as not written up rather than given a stub.
MAX_NARRATED_COMMUNITIES = 150
NARRATIVE_CONCURRENCY = 4
NARRATIVE_TIMEOUT_SECONDS = 180

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Three parsers, because a location is read in three different settings. Each
# captures (path, start, end) in that order.
#
# A location the indexer produced is exactly `path:12` or `path:12-18` and
# nothing else, so the path is everything before the last `:lines` suffix —
# whatever characters it holds. `app/[slug]/My Page.tsx` is a real path.
_LOCATION_RE = re.compile(r"(.+):(\d+)(?:-(\d+))?")
# In prose there is no fixed end, so a citation is delimited by the backticks
# the prompt asks for, never by a guess at which characters a path may use. It
# must still name a file — end in `.ext` — so `localhost:8000` is an address,
# not a citation.
_CITED_RE = re.compile(r"`([^`\n]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?`")
# A citation written without backticks is still a claim about the code. These
# only use ordinary path characters, and are checked like any other.
_BARE_ANCHOR_RE = re.compile(r"(?<![\w/.-])([\w./-]+\.[A-Za-z0-9]+):(\d+)(?:-(\d+))?\b")
# A URL is an address however it ends: `http://api.example.com:8080` would
# otherwise read as the file `//api.example.com`, line 8080. Never past a
# backtick, so it cannot unpair the backticks around a real citation.
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s`]+")


def _names_source_file(path: str) -> bool:
    """Whether `path` could be a file the indexer read, judged by its suffix.

    A port reads exactly like a line number, so `db.example.com:5432` and
    `127.0.0.1:8000` cannot be told from citations by their shape. Every path
    the model is offered passed the indexer's own `CODE_SUFFIXES` filter, so
    anything ending otherwise — `.com`, `.internal`, `.1` — is not a source
    citation, offered or invented, and is read as prose.
    """
    return PurePosixPath(path).suffix in CODE_SUFFIXES
_NARRATIVE_BLOCK_RE = re.compile(
    r"<!-- archivum:narrative ([0-9a-f]+) -->\n(.*?)\n<!-- /archivum:narrative -->",
    re.DOTALL,
)


def slugify(value: str) -> str:
    return _SLUG_RE.sub("-", value.strip().lower()).strip("-") or "untitled"


def repo_folder(name: str) -> str:
    return f"code/{slugify(name)}"


def _lines(span: str) -> str:
    """`L12-L18` as the reader would write it: `12-18`."""
    parts = [part.strip().lstrip("Ll") for part in span.split("-") if part.strip()]
    if not all(part.isdigit() for part in parts) or not parts:
        return ""
    # A single-line span reads better as one number than as `12-12`.
    if len(parts) == 2 and parts[0] == parts[1]:
        return parts[0]
    return "-".join(parts)


def _source_path(object_: KnowledgeObject, *, repo_root: str = "") -> str:
    """The file this record was read from, relative to the repository."""
    if not object_.citations:
        return ""
    path = object_.citations[0].chunk_id or ""
    if repo_root and path.startswith(repo_root):
        path = path[len(repo_root) :].lstrip("/")
    return path


def _location(object_: KnowledgeObject, *, repo_root: str = "") -> str:
    """Where this record came from, as `path:lines`, relative to the repository.

    Citations store the absolute path the file had on the machine that indexed
    it. Printing that verbatim leaks the deployment's filesystem layout into the
    vault and buries the only part a reader wants — which file, which lines.
    """
    path = _source_path(object_, repo_root=repo_root)
    if not path:
        return ""
    lines = _lines(object_.citations[0].quote or "")
    return f"{path}:{lines}" if lines else path


# ── Tests are not subsystems ─────────────────────────────────────────────────

# Directories whose contents are tests in every ecosystem that uses them.
_TEST_DIRS = frozenset({"test", "tests", "__tests__", "spec", "specs"})
_TEST_FILE_RES = (
    re.compile(r"^test_.+\.py$"),  # pytest
    re.compile(r"^.+_test\.(py|go)$"),  # pytest, go
    re.compile(r"^conftest\.py$"),
    re.compile(r"^.+\.(test|spec)\.[cm]?[jt]sx?$"),  # jest, vitest, mocha
    re.compile(r"^.+_spec\.rb$"),  # rspec
    re.compile(r"^.+[a-z0-9]Tests?\.(java|kt|cs|swift)$"),  # JUnit, xUnit, XCTest
)


def is_test_path(path: str) -> bool:
    """True when a repository-relative path is a test file.

    Read from the path alone, so it works for every language the extractor
    reads without asking the parser what a test is.
    """
    parts = PurePosixPath(path.replace("\\", "/")).parts
    if not parts:
        return False
    if any(part in _TEST_DIRS for part in parts[:-1]):
        return True
    name = parts[-1]
    return any(pattern.match(name) for pattern in _TEST_FILE_RES)


def _is_test_only(
    community: Community,
    objects_by_id: dict[str, KnowledgeObject],
    *,
    repo_root: str = "",
) -> bool:
    """True when every file a cluster was read from is a test.

    A test file and the helpers it defines cluster together, and a page titled
    `icon.test` would then sit beside `icon` as if it were a subsystem of its
    own. Clusters that mix code with its tests keep their page: there the tests
    are part of the account, not all of it.
    """
    paths = [
        _source_path(objects_by_id[member], repo_root=repo_root)
        for member in community.member_ids
        if member in objects_by_id
    ]
    paths = [path for path in paths if path]
    return bool(paths) and all(is_test_path(path) for path in paths)


# ── Tags that say something ──────────────────────────────────────────────────

_LANGUAGES = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".cs": "csharp",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".nix": "nix",
    ".sh": "shell",
}

# Words that appear in every codebase and so tell one cluster from another not
# at all. Kept short on purpose: the frequency count does most of the work.
_TAG_STOPWORDS = frozenset(
    {
        "and", "are", "add", "all", "any", "app", "args", "async", "await", "base",
        "build", "call", "check", "class", "code", "config", "create", "data", "def",
        "default", "dict", "does", "done", "from", "get", "handle", "has", "impl",
        "init", "item", "items", "key", "list", "load", "make", "main", "new", "none",
        "not", "obj", "object", "read", "run", "self", "set", "src", "the", "this",
        "to", "type", "update", "util", "utils", "value", "values", "with", "write",
    }
)
_WORD_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
MAX_TAGS = 7


def _label_words(label: str) -> list[str]:
    words = []
    for chunk in re.split(r"[^A-Za-z0-9]+", label):
        words.extend(word.lower() for word in _WORD_RE.findall(chunk))
    return [
        word
        for word in words
        if len(word) >= 3 and not word.isdigit() and word not in _TAG_STOPWORDS
    ]


def community_tags(
    community: Community,
    objects_by_id: dict[str, KnowledgeObject],
    *,
    repo_root: str = "",
) -> list[str]:
    """Tags read from what the cluster contains, not from the fact it is one.

    Every page used to carry `code, cluster`, which tells a reader and a search
    nothing about which cluster. These come from the members alone — the
    language of their files, the directory they share, the words their names
    are made of — so they are deterministic and cannot claim anything the code
    does not.
    """
    members = [objects_by_id[mid] for mid in community.member_ids if mid in objects_by_id]
    paths = [path for path in (_source_path(m, repo_root=repo_root) for m in members) if path]

    tags: list[str] = ["code"]
    languages = Counter(
        _LANGUAGES[suffix]
        for suffix in (PurePosixPath(path).suffix.lower() for path in paths)
        if suffix in _LANGUAGES
    )
    tags += [language for language, _ in sorted(languages.items(), key=lambda kv: (-kv[1], kv[0]))[:2]]

    directories = Counter(
        PurePosixPath(path).parent.name for path in paths if PurePosixPath(path).parent.name
    )
    if directories:
        area, _ = min(directories.items(), key=lambda kv: (-kv[1], kv[0]))
        tags.append(slugify(area))

    tags.append(slugify(community.label))

    words: Counter[str] = Counter()
    for member in members:
        if member.kind in {"symbol", "type", "file"}:
            words.update(set(_label_words(member.label)))
    tags += [word for word, _ in sorted(words.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_TAGS]]

    unique: list[str] = []
    for tag in tags:
        if tag and tag not in unique and tag != "untitled":
            unique.append(tag)
    return unique[:MAX_TAGS]


# ── The narrative ────────────────────────────────────────────────────────────


def _spans(known_locations: set[str]) -> dict[str, list[tuple[int, int]]]:
    spans: dict[str, list[tuple[int, int]]] = {}
    for location in known_locations:
        match = _LOCATION_RE.fullmatch(location)
        if not match:
            continue
        start = int(match.group(2))
        end = int(match.group(3) or start)
        spans.setdefault(match.group(1), []).append((start, end))
    return spans


def narrative_is_substantive(text: str, *, known_locations: set[str]) -> bool:
    """The guard every cluster page passes before it may be written.

    Substantive means: enough prose to say what the code does, at least one
    `path:line` anchor, and every anchor pointing inside a location the model
    was actually shown. A sentence about the cluster fails on length; a fluent
    narrative that cites a line it invented fails on provenance. Both are
    worse than no page — an absent page is obvious, a wrong one is not.
    """
    text = (text or "").strip()
    if not text:
        return False
    addressed = _URL_RE.sub(" ", text)
    cited = list(_CITED_RE.finditer(addressed))
    # Bare citations are looked for only outside the backticked ones, so a
    # path with a space in it is not read a second time as a shorter path.
    outside = _CITED_RE.sub(" ", addressed)
    anchors = [
        anchor
        for anchor in cited + list(_BARE_ANCHOR_RE.finditer(outside))
        if _names_source_file(anchor.group(1))
    ]
    if not anchors:
        return False
    spans = _spans(known_locations)
    for anchor in anchors:
        start = int(anchor.group(2))
        end = int(anchor.group(3) or start)
        # `geo.py:999-1` is not a range at all. Checked first, because each
        # bound on its own can still land inside a real span.
        if start < 1 or start > end:
            return False
        if not any(lo <= start and end <= hi for lo, hi in spans.get(anchor.group(1), [])):
            return False
    prose = _BARE_ANCHOR_RE.sub(" ", outside)
    return len(re.findall(r"[A-Za-z][A-Za-z'-]*", prose)) >= MIN_NARRATIVE_WORDS


@dataclass(frozen=True)
class Narration:
    """What the model wrote for one cluster, or why there is nothing."""

    text: str
    fingerprint: str
    reason: str = ""


def _members(community: Community, objects_by_id: dict[str, KnowledgeObject]) -> list[KnowledgeObject]:
    members = [objects_by_id[mid] for mid in community.member_ids if mid in objects_by_id]
    members.sort(key=lambda object_: (object_.kind, object_.label))
    return members


def _shown_in_prompt(members: list[KnowledgeObject]) -> list[KnowledgeObject]:
    """The members the model is actually shown, in the order it sees them.

    Symbols and types first: they carry the signatures and docstrings, and are
    what a reader looks for. The prompt and the guard both read this one list,
    so a citation to a member the model never saw cannot pass as a real one.
    """
    return sorted(
        members, key=lambda m: (m.kind not in {"type", "symbol"}, m.kind, m.label)
    )[:MAX_MEMBERS_IN_PROMPT]


def _allowed_locations(members: list[KnowledgeObject], *, repo_root: str) -> set[str]:
    """The `path:lines` a narrative may cite: those of the members it was shown."""
    return {
        location
        for location in (
            _location(member, repo_root=repo_root) for member in _shown_in_prompt(members)
        )
        if ":" in location
    }


def _neighbours(
    community: Community,
    *,
    objects_by_id: dict[str, KnowledgeObject],
    edges: list,
    community_of: dict[str, str],
) -> list[str]:
    """Other clusters this one reaches, each backed by at least one edge."""
    member_ids = set(community.member_ids)
    reached: dict[str, list[str]] = {}
    for edge in sorted(edges, key=lambda e: (e.rel_type, e.src_id, e.dst_id)):
        if (edge.src_id in member_ids) == (edge.dst_id in member_ids):
            continue
        inside, outside = (
            (edge.src_id, edge.dst_id) if edge.src_id in member_ids else (edge.dst_id, edge.src_id)
        )
        other = community_of.get(outside)
        if not other or other == community.label:
            continue
        here = objects_by_id.get(inside)
        there = objects_by_id.get(outside)
        if here is None or there is None:
            continue
        direction = "→" if edge.src_id == inside else "←"
        reached.setdefault(other, []).append(
            f"{here.label} {direction} *{edge.rel_type}* {direction} {there.label}"
        )
    return [
        f"- **{name}**, via {'; '.join(links[:3])}"
        for name, links in sorted(reached.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    ][:MAX_NEIGHBOURS_IN_PROMPT]


def _instruction(
    community: Community,
    *,
    repo_name: str,
    members: list[KnowledgeObject],
    neighbours: list[str],
    repo_root: str,
) -> str:
    ranked = _shown_in_prompt(members)
    rows = []
    for member in ranked:
        where = _location(member, repo_root=repo_root)
        row = f"- `{where}` " if ":" in where else "- "
        row += f"{member.label} ({member.kind})"
        signature = str(member.properties.get("signature") or "").strip()
        summary = str(member.properties.get("summary") or "").strip()
        if signature:
            row += f" — signature: {signature}"
        if summary:
            row += f" — docstring: {summary}"
        rows.append(row)
    example = next((loc for loc in (_location(m, repo_root=repo_root) for m in ranked) if ":" in loc), "")
    connected = "\n".join(neighbours) if neighbours else "- none: the graph shows no edge leaving this cluster"
    return (
        f"These records from the `{repo_name}` repository are more connected to "
        "each other than to the rest of the code. Write the opening of a "
        "reference page about the subsystem they form, for a developer who has "
        "not read it.\n\n"
        "Write two short paragraphs of plain prose, 80 to 200 words in total:\n"
        "1. What this subsystem does and why it exists, judged from the names, "
        "signatures and docstrings below.\n"
        "2. Its key symbols or entry points, each cited with its location in "
        f"backticks exactly as given (for example `{example}`), and how it "
        "connects to the neighbouring subsystems listed below, by name.\n\n"
        "Rules:\n"
        "- Use only what is below. Do not invent behaviour, files, line numbers "
        "or connections. Cite only locations from the list. Name only "
        "neighbours from the list; if there are none, say it stands alone.\n"
        "- Where the names do not show a purpose, say so plainly rather than "
        "guessing — a wrong account is read back later as fact.\n"
        "- No headings, no bullet lists, no preamble. Reply with the prose alone.\n\n"
        f"Members:\n{chr(10).join(rows)}\n\n"
        f"Neighbouring subsystems (each backed by an edge in the graph):\n{connected}\n"
    )


def _existing_narrative(path) -> tuple[str, str]:
    """The fingerprint and narrative a page was last written with, if any."""
    try:
        match = _NARRATIVE_BLOCK_RE.search(path.read_text(encoding="utf-8"))
    except OSError:
        return "", ""
    return (match.group(1), match.group(2).strip()) if match else ("", "")


async def narrate_communities(
    communities: list[Community],
    *,
    repo_name: str,
    objects_by_id: dict[str, KnowledgeObject],
    edges: list,
    community_of: dict[str, str],
    repo_root: str,
    settings: Settings,
) -> dict[str, Narration]:
    """One narrative per cluster, all before any page is written.

    Each cluster is asked for independently, so one failed or thin reply costs
    that cluster its page and nothing else. A cluster whose material is
    unchanged reuses the narrative already on its page.
    """
    provider = settings.llm_synthesis_provider
    model = settings.llm_model
    owner = settings.owner_username or None
    folder = repo_folder(repo_name)
    gate = asyncio.Semaphore(NARRATIVE_CONCURRENCY)

    async def narrate(rank: int, community: Community) -> tuple[str, Narration]:
        members = _members(community, objects_by_id)
        instruction = _instruction(
            community,
            repo_name=repo_name,
            members=members,
            neighbours=_neighbours(
                community, objects_by_id=objects_by_id, edges=edges, community_of=community_of
            ),
            repo_root=repo_root,
        )
        # The date preamble is left out on purpose: it changes daily, and the
        # narrative depends only on the code it describes.
        fingerprint = hashlib.sha256(
            f"{provider}\n{model}\n{instruction}".encode()
        ).hexdigest()[:16]
        known = _allowed_locations(members, repo_root=repo_root)

        cached_fingerprint, cached = _existing_narrative(
            settings.wiki_dir / f"{folder}/{slugify(community.label)}.md"
        )
        if cached_fingerprint == fingerprint and narrative_is_substantive(cached, known_locations=known):
            return community.id, Narration(cached, fingerprint)

        if rank >= MAX_NARRATED_COMMUNITIES:
            return community.id, Narration("", fingerprint, "past this run's narration budget")

        prompt = with_context(
            instruction,
            owner=owner,
            extra={"Repository": repo_name, "Cluster": community.label},
        )
        async with gate:
            try:
                text = (
                    await cli_chat_completion(
                        provider=provider,
                        model=model,
                        prompt=prompt,
                        timeout_seconds=NARRATIVE_TIMEOUT_SECONDS,
                    )
                ).strip()
            except (CliModelError, Exception) as exc:  # noqa: BLE001 - see module docstring
                logger.debug("No narrative for %s: %s", community.label, exc)
                return community.id, Narration("", fingerprint, "the model could not be reached")
        if not narrative_is_substantive(text, known_locations=known):
            return community.id, Narration(
                "", fingerprint, "the model's account was too thin or cited lines it was not shown"
            )
        return community.id, Narration(text, fingerprint)

    results = await asyncio.gather(
        *(narrate(rank, community) for rank, community in enumerate(communities))
    )
    return dict(results)


def render_community_page(
    community: Community,
    *,
    repo_name: str,
    objects_by_id: dict[str, KnowledgeObject],
    edges: list,
    narrative: str,
    fingerprint: str = "",
    repo_root: str = "",
    sibling_pages: dict[str, str] | None = None,
) -> str | None:
    """The page for one cluster, or None when there is nothing worth writing.

    The guard lives here rather than in the caller so that no path can render
    a cluster page around a stub: without a substantive narrative there is no
    page at all.

    `sibling_pages` maps a symbol id to the slug of the cluster page that owns
    it. An edge leaving this cluster links to that page, so sibling subsystems
    are connected by the calls between them; a symbol with no page stays prose,
    because a link to a page that does not exist is a lint finding, not an edge.
    """
    members = _members(community, objects_by_id)
    if not narrative_is_substantive(
        narrative, known_locations=_allowed_locations(members, repo_root=repo_root)
    ):
        return None
    shown = members[:MAX_MEMBERS_PER_PAGE]

    lines = [
        f"# {community.label}",
        "",
        f"Part of [[{repo_folder(repo_name)}/index|{repo_name}]].",
        "",
        # Marked so the next index run can tell whether this narrative still
        # describes the code, and reuse it rather than ask again.
        f"<!-- archivum:narrative {fingerprint or '0'} -->",
        narrative.strip(),
        "<!-- /archivum:narrative -->",
        "",
        "## What is in here",
        "",
    ]

    for object_ in shown:
        where = _location(object_, repo_root=repo_root)
        suffix = f" — `{where}`" if where else ""
        lines.append(f"- **{object_.label}** ({object_.kind}){suffix}")
    if len(members) > len(shown):
        lines.append(f"- …and {len(members) - len(shown)} more.")

    member_ids = set(community.member_ids)
    internal = [
        edge
        for edge in edges
        if edge.src_id in member_ids and edge.dst_id in member_ids
    ]
    if internal:
        lines += ["", "## How they connect", ""]
        for edge in sorted(internal, key=lambda e: (e.rel_type, e.src_id, e.dst_id))[:MAX_MEMBERS_PER_PAGE]:
            src = objects_by_id.get(edge.src_id)
            dst = objects_by_id.get(edge.dst_id)
            if src is None or dst is None:
                continue
            lines.append(
                f"- {src.label} → *{edge.rel_type}* → {dst.label} "
                f"({edge.extraction_method.lower()})"
            )

    # Edges that leave the cluster are the interesting part: they are where this
    # piece of the repository touches everything else, including decisions.
    outward = [
        edge
        for edge in edges
        if (edge.src_id in member_ids) != (edge.dst_id in member_ids)
    ]
    if outward:
        own_slug = f"{repo_folder(repo_name)}/{slugify(community.label)}"
        lines += ["", "## What it reaches", ""]
        for edge in sorted(outward, key=lambda e: (e.rel_type, e.src_id, e.dst_id))[:MAX_SURPRISING]:
            src = objects_by_id.get(edge.src_id)
            dst = objects_by_id.get(edge.dst_id)
            src_label = src.label if src else edge.src_id
            dst_label = dst.label if dst else edge.dst_id
            outside = edge.dst_id if edge.src_id in member_ids else edge.src_id
            sibling = (sibling_pages or {}).get(outside)
            if sibling and sibling != own_slug:
                if outside == edge.dst_id:
                    dst_label = f"[[{sibling}|{dst_label}]]"
                else:
                    src_label = f"[[{sibling}|{src_label}]]"
            lines.append(f"- {src_label} → *{edge.rel_type}* → {dst_label}")

    lines += [
        "",
        "---",
        "",
        "The overview was written by a model from the records listed here and "
        "cites only them; the lists come from the code graph directly.",
        "",
    ]
    return "\n".join(lines)


def render_index_page(
    report: GraphReport,
    *,
    repo_name: str,
    communities: list[Community],
    fixes: list[KnowledgeObject] | None = None,
    not_written: list[tuple[Community, str]] | None = None,
    test_only: list[Community] | None = None,
) -> str:
    lines = [
        f"# {repo_name}",
        "",
        # Deliberately not the absolute path. Pages are portable and shareable,
        # and where the repository happens to sit on this server is a fact about
        # the deployment, not about the code. It stays in the register.
        f"Code memory for the `{repo_name}` repository.",
        "",
        f"- {report.node_count} records, {report.edge_count} relationships",
        f"- {len(report.communities)} clusters",
    ]
    for method, count in sorted(report.by_extraction_method.items()):
        lines.append(f"- {count} {method.lower()}")
    lines += ["", "## Clusters", ""]

    if communities:
        for community in communities:
            slug = f"{repo_folder(repo_name)}/{slugify(community.label)}"
            lines.append(f"- [[{slug}|{community.label}]] — {community.size} records")
    else:
        lines.append("- Nothing clustered yet. Index a larger repository, or check the ingest log.")

    if not_written:
        lines += [
            "",
            "## Not written up",
            "",
            "Clusters with no page this run, because no narrative could be written "
            "that was both substantive and backed by the code. A missing page is "
            "deliberate: it is better than a stub.",
            "",
        ]
        for community, reason in not_written:
            lines.append(f"- {community.label} — {community.size} records ({reason})")

    if test_only:
        records = sum(community.size for community in test_only)
        names = ", ".join(community.label for community in test_only)
        lines += [
            "",
            "## Tests",
            "",
            f"{len(test_only)} cluster{'s' if len(test_only) != 1 else ''} "
            f"({records} records) contain only test files and get no page of their "
            f"own, so they do not compete with the code they test: {names}.",
        ]

    if fixes:
        lines += [
            "",
            "## What broke before",
            "",
            "Trouble this repository has already had, and what settled it.",
            "",
        ]
        for fix in fixes:
            symptom = str(fix.properties.get("symptom", "")) or fix.label
            diagnosis = str(fix.properties.get("diagnosis", ""))
            verified = str(fix.properties.get("verified_by", ""))
            lines.append(f"- **{symptom}**")
            if diagnosis:
                lines.append(f"  - {diagnosis}")
            changed = fix.properties.get("changed_paths") or []
            if changed:
                lines.append(f"  - Changed: {', '.join(str(path) for path in changed)}")
            # Say plainly whether this was checked. An unverified fix is still
            # worth keeping; presenting it as proven would not be.
            lines.append(
                f"  - Verified by `{verified}`" if verified else "  - Not verified by a check"
            )

    if report.surprising_links:
        lines += [
            "",
            "## Connections you would not have predicted",
            "",
            "Scored by how little the two records share with the rest of the graph.",
            "",
        ]
        for link in report.surprising_links[:MAX_SURPRISING]:
            lines.append(
                f"- **{link.src_label}** → *{link.rel_type}* → **{link.dst_label}** "
                f"({link.score:.2f}) — {link.reason}"
            )

    if report.narrative:
        lines += ["", "## In plain language", ""]
        lines.extend(str(line) for line in report.narrative)

    lines += [
        "",
        "---",
        "",
        "Generated from the code graph, deterministically — no model was asked. "
        "Every record above is backed by a citation into a file and a line.",
        "",
    ]
    return "\n".join(lines)


def _is_bookkeeping(
    community: Community, objects_by_id: dict[str, KnowledgeObject]
) -> bool:
    """True when a cluster is only repository metadata, not code."""
    kinds = {
        objects_by_id[member].kind
        for member in community.member_ids
        if member in objects_by_id
    }
    return bool(kinds) and kinds <= _BOOKKEEPING_KINDS


# What marks a page as this indexer's own. The narrative block is written by
# this version; the footer by the version that wrote metadata-only pages. A page
# carrying neither was written by someone else and is never removed here.
_OWNED_MARKERS = (
    "<!-- archivum:narrative ",
    "Generated from the code graph. Edit freely",
)


def _written_by_this_indexer(text: str) -> bool:
    return any(marker in text for marker in _OWNED_MARKERS)


async def _retire_stale_page(slug: str, *, wiki_id: str, settings: Settings) -> bool:
    """Remove a cluster page this indexer wrote earlier and can no longer stand by.

    Skipping a rejected or test-only cluster is not enough on its own: the page
    from the previous run would stay on disk and in search, describing code that
    may no longer exist, while the index says it was not written up. It goes
    through `forget_page` — the same path a deleted file takes — so the row,
    vectors and graph node leave together.

    A marker only says the indexer once wrote the page, and the footer invites
    people to edit it. So the page must also still be the indexer's: its row
    last saved by the agent, and the file unchanged since. A page someone has
    taken over is left stale rather than deleted — stale is wrong, deleted
    notes are gone.
    """
    row = await sqlite.get_page(slug, wiki_id)
    if not row or row.get("authored_by") != "agent":
        return False
    indexed = str(row.get("content") or "")
    path = settings.wiki_dir / f"{slug}.md"
    # An edit the vault watcher has not swept yet still reads as the agent's
    # in the row; the file itself is the newer word.
    if path.exists() and path.read_text(encoding="utf-8", errors="replace") != indexed:
        return False
    if not indexed or not _written_by_this_indexer(indexed):
        return False
    path.unlink(missing_ok=True)
    await forget_page(slug, wiki_id=wiki_id, settings=settings)
    return True


async def _fixes_for(repo: "CodeRepo") -> list[KnowledgeObject]:
    """Remembered repairs that reached this repository's code.

    Fixes live in the vault's scope and reach code through a `bridge` edge, so
    they are found by walking that edge rather than by scope.
    """
    async with sqlite.get_db() as conn:
        knowledge = KnowledgeRepository(conn)
        symbol_ids = {
            object_.id
            for object_ in await knowledge.list_objects(scope=repo.scope, limit=10_000)
        }
        edges = await knowledge.list_relationships(scope="bridge")
        fix_ids = sorted(
            {
                edge.src_id
                for edge in edges
                if edge.rel_type == "fixes" and edge.dst_id in symbol_ids
            }
        )
        found = [await knowledge.get_object(fix_id) for fix_id in fix_ids]
    return [fix for fix in found if fix is not None][:MAX_SURPRISING]


async def write_repo_pages(repo: "CodeRepo", *, settings: Settings) -> int:
    """Write the index and one page per cluster. Returns how many pages landed.

    Page writing never fails the indexing run: the canonical graph is the record
    that matters, and a vault that could not be written is a problem to report,
    not a reason to throw away work that already succeeded.
    """
    async with sqlite.get_db() as conn:
        knowledge = KnowledgeRepository(conn)
        # This repository, the vault that owns it, and the owner root: enough
        # for a decision link to show on the page, and nothing from elsewhere.
        report = await audit_knowledge_graph(
            knowledge,
            scope=repo.scope,
            allowed_scopes={repo.scope, f"wiki:{repo.wiki_id}", SELF_ID},
        )
        objects = await knowledge.list_objects(scope=repo.scope, limit=100_000)
        edges = await knowledge.list_relationships(scope=repo.scope)

    objects_by_id = {object_.id: object_ for object_ in objects}
    fixes = await _fixes_for(repo)
    candidates = [
        community
        for community in report.communities
        if community.size >= MIN_COMMUNITY_SIZE
        and not _is_bookkeeping(community, objects_by_id)
    ]
    test_only = [
        community
        for community in candidates
        if _is_test_only(community, objects_by_id, repo_root=repo.path)
    ]
    communities = [community for community in candidates if community not in test_only]

    community_of = {
        member: community.label
        for community in report.communities
        for member in community.member_ids
    }
    narrations = await narrate_communities(
        communities,
        repo_name=repo.name,
        objects_by_id=objects_by_id,
        edges=edges,
        community_of=community_of,
        repo_root=repo.path,
        settings=settings,
    )

    folder = repo_folder(repo.name)

    def render(community: Community, sibling_pages: dict[str, str] | None = None) -> str | None:
        narration = narrations[community.id]
        return render_community_page(
            community,
            repo_name=repo.name,
            objects_by_id=objects_by_id,
            edges=edges,
            narrative=narration.text,
            fingerprint=narration.fingerprint,
            repo_root=repo.path,
            sibling_pages=sibling_pages,
        )

    # Which clusters get a page is only known once each has been rendered, and
    # a cluster may only link to a sibling that got one. So decide first, then
    # render the pages that will land with their sibling links in place.
    written_up: list[Community] = []
    not_written: list[tuple[Community, str]] = []
    for community in communities:
        if render(community) is None:
            reason = narrations[community.id].reason or "no substantive narrative"
            not_written.append((community, reason))
        else:
            written_up.append(community)
    sibling_pages = {
        member: f"{folder}/{slugify(community.label)}"
        for community in written_up
        for member in community.member_ids
    }
    cluster_pages: list[tuple[str, str, str, list[str]]] = []
    for community in written_up:
        markdown = render(community, sibling_pages)
        assert markdown is not None  # links never change whether a page is written
        cluster_pages.append(
            (
                f"{folder}/{slugify(community.label)}",
                community.label,
                markdown,
                community_tags(community, objects_by_id, repo_root=repo.path),
            )
        )
    if not_written:
        logger.warning(
            "%d of %d clusters in %s were not written up (first: %s — %s)",
            len(not_written),
            len(communities),
            repo.name,
            not_written[0][0].label,
            not_written[0][1],
        )

    pages: list[tuple[str, str, str, list[str]]] = [
        (
            f"{folder}/index",
            repo.name,
            render_index_page(
                report,
                repo_name=repo.name,
                communities=written_up,
                fixes=fixes,
                not_written=not_written,
                test_only=test_only,
            ),
            ["code", "repo"],
        ),
        *cluster_pages,
    ]

    written = 0
    for slug, title, markdown, tags in pages:
        try:
            path = settings.wiki_dir / f"{slug}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                ensure_frontmatter(markdown, title=title, tags=tags), encoding="utf-8"
            )
            # Same indexing path as a page written by hand. No distillation:
            # this page came out of the graph, and feeding it back in would
            # propose the repository's own structure as things to remember.
            await reindex_page(
                slug,
                wiki_id=repo.wiki_id,
                settings=settings,
                force=True,
                authored_by="agent",
                reason="code-graph",
                distill=False,
            )
            written += 1
        except Exception as exc:  # noqa: BLE001 - the canonical graph is already saved
            logger.warning("Could not write code page %s: %s", slug, exc)

    # A cluster that has no page this run must not keep the one it had. Never a
    # slug written above: two clusters can share a label, and the index is not
    # a cluster page at all.
    written_slugs = {slug for slug, _, _, _ in pages}
    stale = {f"{folder}/{slugify(community.label)}" for community, _ in not_written}
    stale |= {f"{folder}/{slugify(community.label)}" for community in test_only}
    for slug in sorted(stale - written_slugs):
        try:
            if await _retire_stale_page(slug, wiki_id=repo.wiki_id, settings=settings):
                logger.info("Removed stale code page %s", slug)
        except Exception as exc:  # noqa: BLE001 - same contract as writing
            logger.warning("Could not remove stale code page %s: %s", slug, exc)

    return written
