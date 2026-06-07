import asyncio
import unittest

from archivum.ingest.events import publish, subscribe


class IngestEventsTests(unittest.TestCase):
    def test_subscriber_receives_only_matching_wiki_events(self):
        async def run_test():
            async with subscribe("default") as queue:
                await publish("other", {"type": "start", "file": "other.pdf"})
                await publish("default", {"type": "start", "file": "resume.pdf"})

                event = await asyncio.wait_for(queue.get(), timeout=0.1)

                self.assertEqual(event["type"], "start")
                self.assertEqual(event["file"], "resume.pdf")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
