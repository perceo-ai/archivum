import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from archivum.ingest.agent import ExtractionResult, WikiAgent, WikiPage
from archivum.ingest.parsers import ParsedDoc
from archivum.ingest.pipeline import ingest, _sync_extracted_result_to_knowledge
from archivum.knowledge.personal_root import SELF_ID
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


class IngestPipelineTests(unittest.TestCase):
    def test_fallback_extraction_adds_entities_and_relationships_for_graph(self):
        agent = WikiAgent(SimpleNamespace(llm_extraction_provider="test"))
        doc = ParsedDoc(
            text=(
                "Jane Doe is a product designer at Archivum. "
                "Jane Doe built Knowledge Graph Search with OpenAI."
            ),
            source="resume.pdf",
            metadata={"title": "resume", "filename": "resume.pdf"},
        )

        result = agent._fallback_extraction(doc)

        entity_names = {entity["name"] for entity in result.entities}
        self.assertIn("Jane Doe", entity_names)
        self.assertIn("Archivum", entity_names)
        self.assertIn("Knowledge Graph Search", entity_names)
        self.assertGreaterEqual(len(result.relationships), 2)

    def test_ingest_uses_display_source_for_logs_events_and_extraction(self):
        async def run_test():
            events = []
            settings = SimpleNamespace(
                wiki_dir=Path(tempfile.mkdtemp()),
                llm_extraction_provider="test",
                llm_model="test-model",
            )
            parsed_doc_holder = {}

            async def fake_parse_source(source):
                from archivum.ingest.parsers import ParsedDoc

                return ParsedDoc(
                    text="Jane Doe built Archivum.",
                    source=str(source),
                    metadata={"type": "pdf"},
                )

            class FakeAgent:
                async def extract(self, doc):
                    parsed_doc_holder["doc"] = doc
                    return ExtractionResult(
                        pages=[
                            WikiPage(
                                slug="jane-doe",
                                title="Jane Doe",
                                content="# Jane Doe\n\nJane Doe built [[Archivum]].",
                                tags=["person"],
                            )
                        ],
                        entities=[
                            {"name": "Jane Doe", "type": "person"},
                            {"name": "Archivum", "type": "tech"},
                        ],
                        relationships=[
                            {"from": "Jane Doe", "to": "Archivum", "type": "related_to"}
                        ],
                    )

            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                Path(tmp.name).write_text("fake pdf content", encoding="utf-8")

                with (
                    patch("archivum.ingest.pipeline.parse_source", side_effect=fake_parse_source),
                    patch("archivum.ingest.pipeline.get_agent", return_value=FakeAgent()),
                    patch("archivum.ingest.pipeline.sqlite.create_ingest_log", new=AsyncMock(return_value=42)) as create_log,
                    patch("archivum.ingest.pipeline.sqlite.update_ingest_log", new=AsyncMock()),
                    patch("archivum.ingest.pipeline.sqlite.get_page", new=AsyncMock(return_value=None)),
                    patch("archivum.ingest.pipeline.sqlite.upsert_page", new=AsyncMock(return_value=(1, True))),
                    patch("archivum.ingest.pipeline.qdrant.upsert_page", new=AsyncMock(return_value=1)),
                    patch("archivum.ingest.pipeline.graph.upsert_page", new=AsyncMock()),
                    patch("archivum.ingest.pipeline.graph.upsert_entity", new=AsyncMock()),
                    patch("archivum.ingest.pipeline.graph.add_entity_relation", new=AsyncMock()),
                    patch("archivum.ingest.pipeline.graph.add_mention", new=AsyncMock()),
                    patch("archivum.ingest.pipeline.graph.add_reference", new=AsyncMock()),
                ):
                    await ingest(
                        Path(tmp.name),
                        "default",
                        lambda event: events.append(event) or asyncio.sleep(0),
                        settings,
                        source_name="resume.pdf",
                    )

            create_log.assert_awaited_once_with("file", "resume.pdf", "default")
            self.assertEqual(events[0]["file"], "resume.pdf")
            self.assertEqual(events[1]["source"], "resume.pdf")
            self.assertEqual(parsed_doc_holder["doc"].source, "resume.pdf")
            self.assertEqual(parsed_doc_holder["doc"].metadata["title"], "resume")
            self.assertEqual(parsed_doc_holder["doc"].metadata["filename"], "resume.pdf")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()


@pytest.mark.asyncio
async def test_ingest_canonical_records_preserve_extracted_source_provenance():
    doc = ParsedDoc(
        text="Jane Doe built Archivum.",
        source="resume.pdf",
        metadata={"title": "Resume"},
    )
    result = ExtractionResult(
        pages=[
            WikiPage(
                slug="jane-doe",
                title="Jane Doe",
                content="# Jane Doe\n\nJane Doe built [[Archivum]].",
                tags=["person"],
            )
        ],
        entities=[
            {"name": "Jane Doe", "type": "person"},
            {"name": "Archivum", "type": "project"},
        ],
        relationships=[{"from": "Jane Doe", "to": "Archivum", "type": "built"}],
    )

    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await _sync_extracted_result_to_knowledge(
            repo,
            result=result,
            slug_map={"jane-doe": "jane-doe"},
            doc=doc,
            wiki_id="default",
            source_type="file",
            display_source="resume.pdf",
        )

        source = await repo.get_object("source:default:resumepdf")
        page = await repo.get_object("page:default:jane-doe")
        entity = await repo.get_object("entity:default:jane-doe")
        relationships = await repo.list_relationships(scope="wiki:default")

    assert source is not None
    assert source.kind == "source"
    assert source.extraction_method == "EXTRACTED"
    assert source.citations[0].source_id == source.id
    assert page is not None
    assert page.extraction_method == "EXTRACTED"
    assert page.properties["markdown"].startswith("# Jane Doe")
    assert entity is not None
    assert entity.properties["entity_type"] == "person"
    assert any(
        rel.src_id == SELF_ID
        and rel.dst_id == source.id
        and rel.rel_type == "saved_source"
        for rel in relationships
    )
    assert any(
        rel.src_id == "entity:default:jane-doe"
        and rel.dst_id == "entity:default:archivum"
        and rel.rel_type == "built"
        and rel.extraction_method == "EXTRACTED"
        for rel in relationships
    )
