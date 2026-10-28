import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from deploy.openclaw.stock_ui.proxy import Config, annotate_send, constrain_request, create_app, gateway_headers
from mealie.services.carrie_ui import proxy

HOUSEHOLD = "00000000-0000-4000-8000-000000000001"
CONTEXT = {"startDate": "2026-11-02", "endDate": "2026-11-08", "dinerIds": [], "includeCooking": False}


def fixture_app(household=HOUSEHOLD, lease_seconds=1800, production=False):
    requests = []

    def upstream(request):
        requests.append(request)
        if request.url.path == "/api/users/self":
            if request.headers.get("authorization") != "Bearer fictional":
                return httpx.Response(401)
            return httpx.Response(200, json={"householdId": household})
        if request.url.path.endswith("/control-ui-config.json"):
            return httpx.Response(200, json={"authMode": "trusted-proxy"})
        return httpx.Response(
            200,
            text="<html><head></head><body>stock</body></html>",
            headers={
                "content-type": "text/html",
                "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
                "x-frame-options": "DENY",
                "set-cookie": "secret=never-forward",
            },
        )

    config = (
        Config(
            HOUSEHOLD,
            lease_seconds=lease_seconds,
            production=True,
            prefix="/carrie",
            origin="https://mealie.example.test",
            parent_origin="https://mealie.example.test",
            gateway="http://172.22.0.1:18792",
            agent="carrie",
            identity="mealie",
        )
        if production
        else Config(HOUSEHOLD, lease_seconds=lease_seconds)
    )
    app = create_app(config, httpx.AsyncClient(transport=httpx.MockTransport(upstream)))
    if production:
        parent = FastAPI()
        parent.mount("/carrie", app)
        app = parent
    return TestClient(app, base_url=config.origin), requests


def login(client):
    response = client.post(
        "/__mealie__/auth",
        headers={
            "origin": "http://localhost:3000",
            "authorization": "Bearer fictional",
        },
    )
    assert response.status_code == 200
    return response.json()["lease"]


def test_explicit_loopback_configuration():
    for url in [
        "http://example.com",
        "https://localhost",
        "http://user:pass@localhost",
        "http://localhost/path",
        "http://localhost?token=x",
        'http://localhost:3000"bad',
        "http://localhost:",
    ]:
        with pytest.raises(ValueError):
            Config(HOUSEHOLD, gateway=url)
    with pytest.raises(ValueError):
        Config("")


def test_auth_requires_mealie_origin_valid_token_and_household():
    client, _ = fixture_app()
    assert client.post("/__mealie__/auth").status_code == 403
    assert client.post("/__mealie__/auth", headers={"origin": "http://localhost:3000"}).status_code == 401
    assert (
        client.post(
            "/__mealie__/auth", headers={"origin": "http://localhost:3000", "authorization": "Bearer wrong"}
        ).status_code
        == 403
    )
    other, _ = fixture_app(household="another-household")
    assert (
        other.post(
            "/__mealie__/auth", headers={"origin": "http://localhost:3000", "authorization": "Bearer fictional"}
        ).status_code
        == 403
    )


def test_assets_are_public_but_dynamic_requests_need_lease():
    client, requests = fixture_app()
    response = client.get("/new")
    assert response.status_code == 200
    assert "bridge.js" in response.text
    assert "frame-ancestors http://localhost:3000" in response.headers["content-security-policy"]
    assert "x-frame-options" not in response.headers
    assert "set-cookie" not in response.headers
    assert "x-mealie-user" not in requests[-1].headers
    assert client.get("/control-ui-config.json").status_code == 401
    lease = login(client)
    response = client.get(
        "/control-ui-config.json",
        headers={
            "X-Mealie-Lease": lease,
            "x-mealie-user": "admin",
            "x-openclaw-scopes": "operator.admin",
            "Cookie": "private=secret",
        },
    )
    assert response.status_code == 200
    assert requests[-1].headers["x-mealie-user"] == "mealie-dev"
    assert "operator.admin" not in requests[-1].headers["x-openclaw-scopes"]
    assert not requests[-1].headers.get("cookie")
    assert "authorization" not in requests[-1].headers


def test_expired_leases_fail_closed():
    client, _ = fixture_app(lease_seconds=-1)
    lease = login(client)
    assert client.get("/control-ui-config.json", headers={"X-Mealie-Lease": lease}).status_code == 401


def test_thread_deep_link_loads_public_shell_without_identity():
    client, requests = fixture_app()
    response = client.get("/chat/carrie-dev/fictional-thread")
    assert response.status_code == 200
    assert "bridge.js" in response.text
    assert requests[-1].url.path == "/new"
    assert "x-mealie-user" not in requests[-1].headers


def test_revoked_leases_fail_closed():
    client, _ = fixture_app()
    lease = login(client)
    assert (
        client.delete(
            "/__mealie__/auth", headers={"origin": "https://evil.example", "X-Mealie-Lease": lease}
        ).status_code
        == 403
    )
    assert (
        client.delete(
            "/__mealie__/auth", headers={"origin": "http://localhost:3000", "X-Mealie-Lease": lease}
        ).status_code
        == 204
    )
    assert client.get("/control-ui-config.json", headers={"X-Mealie-Lease": lease}).status_code == 401


def test_host_and_websocket_origin_checks():
    client, _ = fixture_app()
    assert client.get("/new", headers={"host": "evil.example"}).status_code == 403
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/", headers={"origin": "https://evil.example"}):
            pass


def test_annotation_is_per_message_and_preserves_retry_identity():
    original = {
        "type": "req",
        "id": "one",
        "method": "chat.send",
        "params": {
            "sessionKey": "agent:carrie-dev:dashboard:fictional",
            "message": "/reset",
            "idempotencyKey": "retry-1",
            "__mealieContext": CONTEXT,
        },
    }
    result = annotate_send(original, "carrie-dev")
    assert "__mealieContext" not in result["params"]
    assert result["params"]["idempotencyKey"] == "retry-1"
    assert result["params"]["deliver"] is False
    assert not result["params"]["message"].startswith("/")
    assert json.dumps(CONTEXT, separators=(",", ":")) in result["params"]["message"]
    assert original["params"]["message"] == "/reset"
    with pytest.raises(ValidationError):
        annotate_send({**original, "params": {**original["params"], "__mealieContext": None}}, "carrie-dev")
    with pytest.raises(ValueError):
        annotate_send({**original, "params": {**original["params"], "sessionKey": "agent:private:main"}}, "carrie-dev")


def test_gateway_headers_are_session_only():
    headers = gateway_headers(Config(HOUSEHOLD))
    assert headers["x-openclaw-scopes"] == "operator.sessions.read,operator.sessions.write"
    assert "authorization" not in headers


@pytest.mark.parametrize("method", ["config.set", "tools.invoke", "cron.add", "sessions.delete"])
def test_unsupported_mutations_are_blocked(method):
    with pytest.raises(ValueError):
        constrain_request({"method": method, "params": {}})


@pytest.mark.parametrize(
    "params",
    [
        {"agentRuntime": "codex"},
        {"permissionMode": "unrestricted"},
        {"toolOverrides": {"exec": True}},
        {"attachments": [{"data": "fictional"}]},
        {"cwd": "/tmp"},
    ],
)
def test_chat_cannot_expand_execution_access(params):
    with pytest.raises(ValueError):
        constrain_request({"method": "chat.send", "params": params})


def test_thread_organization_does_not_allow_privilege_changes():
    constrain_request({"method": "sessions.patch", "params": {"key": "example", "label": "Weekly plan"}})
    with pytest.raises(ValueError):
        constrain_request({"method": "sessions.patch", "params": {"key": "example", "model": "another-model"}})


def test_new_conversation_requires_context_and_fixed_agent():
    frame = {
        "method": "sessions.create",
        "params": {"agentId": "carrie-dev", "task": "Plan next week", "__mealieContext": CONTEXT},
    }
    result = annotate_send(frame, "carrie-dev")
    assert "Mealie planner context" in result["params"]["task"]
    assert "__mealieContext" not in result["params"]
    with pytest.raises(ValueError):
        annotate_send({**frame, "params": {**frame["params"], "agentId": "private"}}, "carrie-dev")
    with pytest.raises(ValidationError):
        annotate_send({**frame, "params": {"agentId": "carrie-dev", "task": "Plan next week"}}, "carrie-dev")


def production_login(client):
    return client.post(
        "/carrie/__mealie__/auth",
        headers={"origin": "https://mealie.example.test", "authorization": "Bearer fictional"},
    )


def test_production_mount_requires_auth_and_keeps_gateway_private():
    client, requests = fixture_app(production=True)
    for path in ("new", "assets/main.js", "__mealie__/bridge.js", "chat/carrie/test"):
        assert client.get("/carrie/" + path).status_code == 401
    assert not requests
    response = production_login(client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for flag in ("Secure", "HttpOnly", "SameSite=strict", "Path=/carrie/"):
        assert flag in cookie
    lease = response.json()["lease"]
    response = client.get("/carrie/chat/carrie/test")
    assert response.status_code == 200
    assert 'src="/carrie/__mealie__/bridge.js"' in response.text
    assert 'data-agent="carrie"' in response.text
    assert requests[-1].url.path == "/carrie/new"
    assert "x-mealie-user" not in requests[-1].headers
    assert "x-openclaw-scopes" not in requests[-1].headers
    assert requests[-1].headers["x-forwarded-for"] == "192.0.2.1"
    assert requests[-1].headers["x-forwarded-proto"] == "https"
    assert requests[-1].headers["x-forwarded-host"] == "mealie.example.test"
    assert client.get("/carrie/control-ui-config.json").status_code == 401
    response = client.get("/carrie/control-ui-config.json", headers={"X-Mealie-Lease": lease})
    assert response.status_code == 200
    assert requests[-1].headers["x-mealie-user"] == "mealie"
    assert requests[-1].headers["x-forwarded-proto"] == "https"
    assert not requests[-1].headers.get("cookie")
    assert "authorization" not in requests[-1].headers
    for path in ("api/config", "sw.js", "__openclaw__/unknown", "tools/invoke"):
        assert client.get("/carrie/" + path, headers={"X-Mealie-Lease": lease}).status_code == 404
    client.delete(
        "/carrie/__mealie__/auth",
        headers={"origin": "https://mealie.example.test", "X-Mealie-Lease": lease},
    )
    assert client.get("/carrie/new").status_code == 401


def test_production_asset_fetch_accepts_per_panel_lease_without_cookie():
    client, requests = fixture_app(production=True)
    lease = production_login(client).json()["lease"]
    client.cookies.clear()
    assert client.get("/carrie/assets/theme.json").status_code == 401
    response = client.get("/carrie/assets/theme.json", headers={"X-Mealie-Lease": lease})
    assert response.status_code == 200
    assert "x-mealie-user" not in requests[-1].headers
    assert "x-openclaw-scopes" not in requests[-1].headers


def test_production_rejects_other_origins_and_households():
    client, _ = fixture_app(production=True)
    response = client.post(
        "/carrie/__mealie__/auth",
        headers={"origin": "https://evil.example", "authorization": "Bearer fictional"},
    )
    assert response.status_code == 403
    other, _ = fixture_app(production=True, household="other-household")
    assert production_login(other).status_code == 403


@pytest.mark.parametrize("method", ["config.get", "exec.approvals.get", "secrets.list", "cron.list"])
def test_sensitive_read_methods_are_not_implicitly_allowed(method):
    with pytest.raises(ValueError):
        constrain_request({"method": method, "params": {}})


def test_production_websocket_scopes_context_and_denied_operations(monkeypatch):
    forwarded = []
    connection = {}

    class Gateway:
        def __init__(self):
            self.queue = asyncio.Queue()

        async def send(self, raw):
            frame = json.loads(raw)
            forwarded.append(frame)
            payload = {"type": "hello-ok", "auth": {"scopes": proxy.SCOPES}} if frame["method"] == "connect" else {}
            await self.queue.put(json.dumps({"type": "res", "id": frame["id"], "ok": True, "payload": payload}))

        def __aiter__(self):
            return self

        async def __anext__(self):
            return await self.queue.get()

    @asynccontextmanager
    async def connect(url, **kwargs):
        connection.update(url=url, **kwargs)
        yield Gateway()

    monkeypatch.setattr(proxy, "connect", connect)
    client, _ = fixture_app(production=True)
    lease = production_login(client).json()["lease"]
    with client.websocket_connect(
        "wss://mealie.example.test/carrie/", headers={"origin": "https://mealie.example.test"}
    ) as socket:
        socket.send_json({"type": "mealie-auth", "lease": lease})
        socket.send_json({"type": "req", "id": "hello", "method": "connect", "params": {}})
        assert socket.receive_json()["ok"]
        assert connection["url"] == "ws://172.22.0.1:18792/carrie/"
        assert connection["additional_headers"]["x-mealie-user"] == "mealie"
        for method, params in [
            ("config.get", {}),
            ("tools.invoke", {}),
            ("chat.history", {"sessionKey": "agent:private:main"}),
            ("chat.startup", {"shortId": "fictional-thread", "agentId": "private"}),
            ("chat.send", {"sessionKey": "agent:carrie:test", "message": "Missing view"}),
        ]:
            socket.send_json({"type": "req", "id": "denied", "method": method, "params": params})
            assert socket.receive_json()["ok"] is False
        assert len(forwarded) == 1
        # A reopened stock UI uses startup rather than a normal history request.
        # This read requires no shared planner context, unlike sending a message.
        startup = {
            "type": "req",
            "id": "restore",
            "method": "chat.startup",
            "params": {"shortId": "fictional-thread", "agentId": "carrie", "limit": 100},
        }
        socket.send_json(startup)
        assert socket.receive_json()["ok"]
        assert forwarded[-1] == startup
        socket.send_json(
            {
                "type": "req",
                "id": "send",
                "method": "chat.send",
                "params": {"sessionKey": "agent:carrie:test", "message": "Review", "__mealieContext": CONTEXT},
            }
        )
        assert socket.receive_json()["ok"]
        assert "Mealie planner context" in forwarded[-1]["params"]["message"]
        assert forwarded[-1]["params"]["deliver"] is False
