import aiosqlite
import pytest

from archivum.knowledge.repository import init_knowledge_schema
from archivum.knowledge.suggestions import SuggestionRepository, init_suggestion_schema


@pytest.mark.asyncio
async def test_suggestion_can_be_accepted_once():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related\n\n- [[Beta]]",
            proposed_objects=[],
            citations=[],
        )
        await repo.accept_suggestion(suggestion.id)
        loaded = await repo.get_suggestion(suggestion.id)
        assert loaded.status == "accepted"
