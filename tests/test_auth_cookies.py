from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import Response

from archivum.api.auth import _set_csrf_cookie
from archivum.main import _CSRFProtection


class AuthCookieTests(unittest.TestCase):
    def test_csrf_cookie_lasts_as_long_as_refresh_cookie(self) -> None:
        response = Response()
        settings = SimpleNamespace(access_token_expire_minutes=15, refresh_token_expire_days=7)

        _set_csrf_cookie(response, "csrf-value", settings)

        self.assertIn("Max-Age=604800", response.headers["set-cookie"])

    def test_refresh_endpoint_can_restore_without_existing_csrf_cookie(self) -> None:
        app = FastAPI()
        app.add_middleware(_CSRFProtection)

        @app.post("/api/auth/refresh")
        async def refresh() -> dict[str, str]:
            return {"detail": "ok"}

        client = TestClient(app)
        client.cookies.set("refresh_token", "existing-refresh")

        response = client.post("/api/auth/refresh")

        self.assertEqual(200, response.status_code)


if __name__ == "__main__":
    unittest.main()
