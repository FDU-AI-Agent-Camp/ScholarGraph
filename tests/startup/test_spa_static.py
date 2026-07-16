"""Unit tests for SPA static hosting helper."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.startup.spa_static import mount_frontend_spa, resolve_frontend_dist_dir


def test_mount_frontend_spa_noop_without_index(tmp_path: Path) -> None:
    app = FastAPI()
    assert mount_frontend_spa(app, dist_dir=tmp_path) is False


def test_mount_frontend_spa_serves_index_and_assets(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (assets / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.ico").write_bytes(b"ico")

    app = FastAPI()

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"ok": "1"}

    assert mount_frontend_spa(app, dist_dir=dist) is True
    client = TestClient(app)

    assert client.get("/api/v1/health").json() == {"ok": "1"}
    assert client.get("/").text == "<html>spa</html>"
    assert client.get("/papers/abc").text == "<html>spa</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/favicon.ico").content == b"ico"


def test_resolve_frontend_dist_dir_type() -> None:
    result = resolve_frontend_dist_dir()
    assert result is None or (result / "index.html").is_file()
