from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_nginx_proxies_api_to_backend() -> None:
    dockerfile = (ROOT / "apps" / "frontend" / "Dockerfile").read_text()

    assert "location /api/" in dockerfile
    assert "proxy_pass http://backend:8000" in dockerfile


def test_the_installer_is_proxied_rather_than_swallowed_by_the_spa():
    """`curl .../install | sh` hits the frontend container first.

    Nginx sends everything that is not /api/ to index.html, so without an
    explicit location the install line pipes a web page into a shell. The
    headline setup path is unusable in the default Compose deployment.
    """
    dockerfile = (
        Path(__file__).resolve().parents[1] / "apps" / "frontend" / "Dockerfile"
    ).read_text()

    assert "location ^~ /install" in dockerfile
    assert dockerfile.index("location ^~ /install") < dockerfile.index("location / {")


def test_uploads_are_not_capped_at_nginx_default():
    """Nginx defaults to 1m. A repository archive is larger than that, so
    `archivum index` got a 413 before the backend ever saw the request."""
    dockerfile = (
        Path(__file__).resolve().parents[1] / "apps" / "frontend" / "Dockerfile"
    ).read_text()

    assert "client_max_body_size" in dockerfile
