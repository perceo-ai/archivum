from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_nginx_proxies_api_to_backend() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()

    assert "location /api/" in dockerfile
    assert "proxy_pass http://backend:8000" in dockerfile
