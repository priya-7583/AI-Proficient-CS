from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = Settings(
        app_name="Test URL Shortener",
        db_path=str(tmp_path / "test.db"),
        short_code_length=6,
        create_limit_per_minute=3,
        jwt_secret="test-jwt-secret-at-least-32-bytes",
    )
    app = create_app(settings)
    return TestClient(app)
