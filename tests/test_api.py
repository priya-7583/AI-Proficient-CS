from __future__ import annotations

import jwt
from fastapi.testclient import TestClient

from app.config import Settings


def _auth_headers(client: TestClient) -> dict[str, str]:
    settings: Settings = client.app.state.settings
    return {"x-api-key": settings.api_key}


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db_ok"] is True


def test_create_resolve_stats_flow(client: TestClient) -> None:
    headers = _auth_headers(client)
    created = client.post(
        "/api/v1/links",
        json={"original_url": "https://example.com/docs", "created_by": "qa"},
        headers=headers,
    )
    assert created.status_code == 201
    code = created.json()["short_code"]

    redirect = client.get(f"/{code}", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "https://example.com/docs"

    stats = client.get(f"/api/v1/links/{code}/stats")
    assert stats.status_code == 200
    body = stats.json()
    assert body["total_clicks"] == 1


def test_idempotent_create_same_user_url(client: TestClient) -> None:
    headers = _auth_headers(client)
    payload = {"original_url": "https://example.com/idempotent", "created_by": "owner-a"}

    first = client.post("/api/v1/links", json=payload, headers=headers)
    second = client.post("/api/v1/links", json=payload, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["short_code"] == second.json()["short_code"]
    assert second.json()["already_exists"] is True


def test_alias_conflict_returns_409(client: TestClient) -> None:
    headers = _auth_headers(client)
    first = client.post(
        "/api/v1/links",
        json={"original_url": "https://example.com/a", "custom_alias": "alias123"},
        headers=headers,
    )
    second = client.post(
        "/api/v1/links",
        json={"original_url": "https://example.com/b", "custom_alias": "alias123"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_rate_limit_returns_429(client: TestClient) -> None:
    headers = _auth_headers(client)
    one = client.post("/api/v1/links", json={"original_url": "https://example.com/1"}, headers=headers)
    two = client.post("/api/v1/links", json={"original_url": "https://example.com/2"}, headers=headers)
    three = client.post("/api/v1/links", json={"original_url": "https://example.com/3"}, headers=headers)
    four = client.post("/api/v1/links", json={"original_url": "https://example.com/4"}, headers=headers)

    assert one.status_code == 201
    assert two.status_code == 201
    assert three.status_code == 201
    assert four.status_code == 429


def test_deactivate_link_blocks_resolution(client: TestClient) -> None:
    headers = _auth_headers(client)
    created = client.post("/api/v1/links", json={"original_url": "https://example.com/kill"}, headers=headers)
    code = created.json()["short_code"]

    deact = client.delete(f"/api/v1/links/{code}", headers=headers)
    assert deact.status_code == 200
    assert deact.json()["deactivated"] is True

    resolve = client.get(f"/{code}", follow_redirects=False)
    assert resolve.status_code == 404


def test_mutating_endpoints_require_auth(client: TestClient) -> None:
    create = client.post("/api/v1/links", json={"original_url": "https://example.com/auth"})
    assert create.status_code == 401


def test_jwt_writer_role_can_mutate(client: TestClient) -> None:
    settings: Settings = client.app.state.settings
    token = jwt.encode(
        {"sub": "qa-user", "role": "writer"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    headers = {"authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/links",
        json={"original_url": "https://example.com/jwt"},
        headers=headers,
    )
    assert created.status_code == 201

    code = created.json()["short_code"]
    deact = client.delete(f"/api/v1/links/{code}", headers=headers)
    assert deact.status_code == 200
