"""Project editable Markdown pages into the canonical knowledge store."""

from __future__ import annotations

import re

from archivum.ingest.agent import slugify
from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository
from archivum.linting import WIKILINK_RE, normalize_wikilink_target


_PROJECT_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n.*?^type:\s*project\s*$.*?^---\s*$",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _page_id(wiki_id: str, slug: str) -> str:
    return f"page:{wiki_id}:{slug}"


def _citation(source_id: str, quote: str, start: int | None = None) -> Citation:
    return Citation(
        source_id=source_id,
        chunk_id=source_id,
        span_start=start,
        span_end=start + len(quote) if start is not None else None,
        quote=quote,
    )


async def sync_page_to_knowledge(
    repo: KnowledgeRepository, *, slug: str, title: str, markdown: str, wiki_id: str
) -> None:
    """Upsert a user-authored page and its Markdown links into canonical knowledge."""
    page_id = _page_id(wiki_id, slug)
    scope = f"wiki:{wiki_id}"
    await repo.upsert_object(
        KnowledgeObject(
            id=page_id,
            kind="page",
            label=title,
            scope=scope,
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[_citation(page_id, title)],
            properties={"slug": slug, "wiki_id": wiki_id},
        )
    )

    await ensure_personal_root(repo, wiki_id=wiki_id)
    await repo.delete_relationships(
        src_id=SELF_ID,
        dst_id=page_id,
        rel_types={"authored_thought", "owns_project"},
    )
    await repo.delete_relationships(src_id=page_id, rel_types={"references", "mentions"})
    relationship_type = "owns_project" if _PROJECT_FRONTMATTER_RE.search(markdown) else "authored_thought"
    await link_to_self(
        repo,
        page_id,
        relationship_type,
        citation=_citation(page_id, title),
    )

    await _link_named_entities(repo, page_id=page_id, markdown=markdown, scope=scope)

    wikilinks = sorted({target.strip() for target in WIKILINK_RE.findall(markdown) if target.strip()})
    linked = {_page_id(wiki_id, normalize_wikilink_target(target)) for target in wikilinks}
    await _link_named_pages(
        repo, page_id=page_id, title=title, markdown=markdown, scope=scope, linked=linked
    )

    for target in wikilinks:
        target_slug = normalize_wikilink_target(target)
        if not target_slug or target_slug == slug:
            continue
        target_id = _page_id(wiki_id, target_slug)
        start = markdown.find(f"[[{target}")
        await repo.upsert_relationship(
            KnowledgeRelationship(
                id=f"rel:{page_id}:references:{target_id}",
                src_id=page_id,
                dst_id=target_id,
                rel_type="references",
                scope=scope,
                confidence=1.0,
                extraction_method="USER_AUTHORED",
                citations=[_citation(page_id, target, start if start >= 0 else None)],
                properties={},
            )
        )


async def rename_page_in_knowledge(
    repo: KnowledgeRepository,
    *,
    old_slug: str,
    new_slug: str,
    title: str,
    markdown: str,
    wiki_id: str,
) -> None:
    """Replace a renamed page's canonical ID and its incident relationships."""
    await remove_page_from_knowledge(repo, slug=old_slug, wiki_id=wiki_id)
    await sync_page_to_knowledge(
        repo,
        slug=new_slug,
        title=title,
        markdown=markdown,
        wiki_id=wiki_id,
    )


async def remove_page_from_knowledge(
    repo: KnowledgeRepository, *, slug: str, wiki_id: str
) -> None:
    """Remove a deleted page and every relationship that could expose it."""
    await repo.delete_object(_page_id(wiki_id, slug))


# Short labels occur inside ordinary prose constantly — "Go", "Make", "Set" —
# and matching them produces edges that say nothing. Acronyms are the exception:
# "JWT" and "XDG" are distinctive as long as the case has to agree, and skipping
# every short label left real entities permanently cut off from the vault.
_MIN_ENTITY_LABEL = 4
_MIN_ACRONYM_LABEL = 2
_MAX_ENTITY_SCAN = 2000


def _is_acronym(label: str) -> bool:
    return len(label) >= _MIN_ACRONYM_LABEL and label.isupper() and label.isalnum()


def _names(needle: str, haystack: str) -> bool:
    # Whole words only: "Make" must not match "makeshift".
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


async def _link_named_entities(
    repo: KnowledgeRepository, *, page_id: str, markdown: str, scope: str
) -> None:
    """Link a page to the entities it names.

    Ingest writes these when it extracts, but that only covers pages that came
    from an ingested document — and reindexing rewrites a page's citations, so
    anything recovered from shared provenance does not survive a reconcile.
    Reading the page gives the same answer every time, from the file on disk,
    without a model.

    Without this the entity graph floats: pages hang off the owner, entities
    hang off other entities, and the two halves never meet.
    """
    entities = [
        obj
        for obj in await repo.list_objects(kind="entity", scope=scope, limit=_MAX_ENTITY_SCAN)
        if len(obj.label.strip()) >= _MIN_ENTITY_LABEL or _is_acronym(obj.label.strip())
    ]
    if not entities:
        return

    lowered = markdown.lower()
    named = []
    for entity in entities:
        label = entity.label.strip()
        # An acronym has to be written as one; a longer name can be written
        # however the author felt like writing it.
        acronym = _is_acronym(label)
        haystack = markdown if acronym else lowered
        needle = label if acronym else label.lower()
        if _names(needle, haystack):
            named.append((entity, label))
    if not named:
        return

    # One transaction for the page's whole set. A commit per edge turned
    # indexing one page into hundreds of them, all contending for the one
    # write lock with every background worker.
    async with repo.transaction():
        for entity, label in named:
            await repo.upsert_relationship(
                KnowledgeRelationship(
                    id=f"rel:{page_id}:mentions:{entity.id}",
                    src_id=page_id,
                    dst_id=entity.id,
                    rel_type="mentions",
                    scope=scope,
                    confidence=0.6,
                    # Read off the page rather than stated by it.
                    extraction_method="INFERRED",
                    citations=[_citation(page_id, label)],
                    properties={"matched": label},
                ),
                commit=False,
            )


def is_nameable_title(title: str) -> bool:
    """Whether a page title is distinctive enough to find in someone's prose.

    Generated code pages are titled after identifiers — "client", "update",
    "layout" — and a bare lowercase word like that is indistinguishable from
    ordinary prose. A title with any capital, punctuation or a second word
    ("Archductor", "workspaceBriefing", "Archivum MCP") is what a person
    writes when they mean that page.
    """
    if _is_acronym(title):
        return True
    if len(title) < _MIN_ENTITY_LABEL:
        return False
    return not (title.isalpha() and title.islower())


async def _link_named_pages(
    repo: KnowledgeRepository,
    *,
    page_id: str,
    title: str,
    markdown: str,
    scope: str,
    linked: set[str],
) -> None:
    """Reference the other pages a page names by title, without brackets.

    Hand-written pages talk about each other in prose — "the Archductor
    Requirements cover this" — and without this they are islands in the graph
    even though their text says exactly how they relate. The edge is recorded,
    never written into the page: the author's file stays as they wrote it.

    Titles match as written, case included. Unlike an entity label, a title is
    the author's own spelling of the name, and it is what separates "Timeline"
    the page from a timeline in a sentence. Pages already wikilinked keep their
    explicit edge; an inferred one must not overwrite it.
    """
    own_title = title.strip()
    # Every title takes part in claiming text, longest first, but only titles
    # of other, unlinked pages become edges. A title that is excluded still
    # uses up what it matches: in "[[design|Ledger Design]]" or a page's own
    # "# Ledger Design" heading, "Ledger" was never named on its own.
    titles: list[tuple[str, str, bool]] = [(page_id, own_title, False)] if own_title else []
    for other_id, label in await repo.list_labels(kind="page", scope=scope):
        other = (label or "").strip()
        if not other:
            continue
        # Two pages can share a title; naming your own title is not a reference.
        excluded = other_id == page_id or other_id in linked or other == own_title
        if excluded or is_nameable_title(other):
            titles.append((other_id, other, not excluded))

    # A wikilink's text belongs to the link the author wrote; the explicit
    # edge already says everything it names.
    remaining = WIKILINK_RE.sub(lambda m: " " * len(m.group(0)), markdown)
    named: list[tuple[str, str, int]] = []
    for other_id, other, creates_edge in sorted(titles, key=lambda t: (-len(t[1]), t[0])):
        pattern = re.compile(rf"(?<!\w){re.escape(other)}(?!\w)")
        match = pattern.search(remaining)
        if match is None:
            continue
        if creates_edge:
            named.append((other_id, other, match.start()))
        remaining = pattern.sub(lambda m: " " * len(m.group(0)), remaining)
    if not named:
        return

    async with repo.transaction():
        for other_id, other, start in named:
            await repo.upsert_relationship(
                KnowledgeRelationship(
                    id=f"rel:{page_id}:references:{other_id}",
                    src_id=page_id,
                    dst_id=other_id,
                    rel_type="references",
                    scope=scope,
                    confidence=0.6,
                    # Read off the page rather than stated by it.
                    extraction_method="INFERRED",
                    citations=[_citation(page_id, other, start)],
                    properties={"matched": other},
                ),
                commit=False,
            )
