from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from omnibot.web.app import STATE_COOKIE, create_app


@pytest.fixture()
def client():
    return TestClient(create_app(bot=None, deploy_marker="test"), base_url="https://dash.example.com")


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/api/health").status_code == 200


def test_cors_rejects_foreign_origin(client):
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"
    ok = client.get("/health", headers={"Origin": "https://dash.example.com"})
    assert ok.headers.get("access-control-allow-origin") == "https://dash.example.com"


def test_login_sets_state_and_encodes_redirect(client):
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code in (302, 307)
    url = urlparse(r.headers["location"])
    q = parse_qs(url.query)
    assert q["redirect_uri"] == ["https://dash.example.com/auth/discord/callback"]
    assert "%2F" in url.query  # actually encoded
    assert r.cookies.get(STATE_COOKIE) == q["state"][0]


def test_callback_without_valid_state_is_rejected(client):
    r = client.get("/auth/discord/callback?code=abc&state=forged", follow_redirects=False)
    assert r.headers["location"] == "/?error=state"


def test_guild_routes_require_login(client):
    assert client.get("/guilds").status_code == 401
    assert client.get("/guilds/123/settings").status_code == 401
