import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class IngestWebSocketTests(unittest.TestCase):
    def test_ingest_websocket_sends_snapshot_and_accepts_ping_control(self):
        settings = get_settings()
        token = create_access_token("owner", "owner", "default", settings)
        app = create_app()

        with patch(
            "archivum.api.ingest.sqlite.list_ingest_logs",
            new=AsyncMock(
                return_value=[
                    {
                        "id": 7,
                        "wiki_id": "default",
                        "source_type": "file",
                        "source_path": "resume.pdf",
                        "status": "running",
                        "pages_created": 0,
                        "pages_updated": 0,
                        "error": None,
                        "created_at": "2026-06-06T00:00:00",
                    }
                ]
            ),
        ):
            client = TestClient(app)
            client.cookies.set("access_token", token)
            with client.websocket_connect("/api/ingest/ws") as ws:
                snapshot = ws.receive_json()
                self.assertEqual(snapshot["type"], "snapshot")
                self.assertEqual(snapshot["logs"][0]["source_path"], "resume.pdf")

                ws.send_json({"type": "control", "action": "ping"})
                pong = ws.receive_json()
                self.assertEqual(pong, {"type": "control_ack", "action": "ping"})


if __name__ == "__main__":
    unittest.main()
