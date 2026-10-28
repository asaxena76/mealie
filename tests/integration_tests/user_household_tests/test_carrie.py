import json
import logging
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from websockets.asyncio.server import serve

from mealie.core.config import get_app_settings
from mealie.schema.carrie.chat import CarrieContext, CarrieSend
from mealie.services.household_services.carrie_service import CarrieConflict, CarrieService, CarrieUnavailable
from tests.utils.fixture_schemas import TestUser

CONTEXT = {"startDate": "2026-11-02", "endDate": "2026-11-08"}
PREFIX = "/api/households/carrie"


def test_anonymous_cannot_access_chat(api_client: TestClient):
    assert api_client.get(f"{PREFIX}/status").status_code == 401
    assert api_client.post(f"{PREFIX}/history", json=CONTEXT).status_code == 401
    assert api_client.post(f"{PREFIX}/stop", json=CONTEXT).status_code == 401
    assert api_client.post(f"{PREFIX}/messages", json=CONTEXT).status_code == 401


def test_disabled_for_unbound_household(api_client: TestClient, unique_user: TestUser, monkeypatch):
    monkeypatch.setattr(get_app_settings(), "CARRIE_HOUSEHOLD_ID", str(uuid4()))
    assert api_client.get(f"{PREFIX}/status", headers=unique_user.token).json() == {
        "enabled": False,
        "stockPath": None,
        "stockAgentId": None,
    }
    assert api_client.post(f"{PREFIX}/history", headers=unique_user.token, json=CONTEXT).status_code == 503


def test_stock_status_exposes_only_relative_route_for_bound_household(api_client, unique_user, monkeypatch):
    settings = get_app_settings()
    monkeypatch.setattr(settings, "CARRIE_HOUSEHOLD_ID", unique_user.household_id)
    monkeypatch.setattr(settings, "CARRIE_STOCK_GATEWAY_URL", "http://172.22.0.1:18792")
    monkeypatch.setattr(settings, "CARRIE_AGENT_ID", "carrie")
    result = api_client.get(f"{PREFIX}/status", headers=unique_user.token)
    assert result.json()["stockPath"] == "/carrie"
    assert result.json()["stockAgentId"] == "carrie"
    assert "172.22" not in result.text
    monkeypatch.setattr(settings, "CARRIE_HOUSEHOLD_ID", str(uuid4()))
    assert api_client.get(f"{PREFIX}/status", headers=unique_user.token).json()["stockPath"] is None


@pytest.mark.parametrize("focused", [True, False])
def test_production_stock_presentation_setting_is_server_only(monkeypatch, focused):
    from mealie.services.carrie_ui import proxy

    settings = get_app_settings()
    monkeypatch.setattr(settings, "CARRIE_HOUSEHOLD_ID", str(uuid4()))
    monkeypatch.setattr(settings, "CARRIE_STOCK_GATEWAY_URL", "http://172.22.0.1:18792")
    monkeypatch.setattr(settings, "CARRIE_STOCK_PUBLIC_ORIGIN", "https://mealie.example.test")
    monkeypatch.setattr(settings, "CARRIE_STOCK_FOCUSED_UI", focused)
    monkeypatch.setattr(proxy, "create_app", lambda config: config)
    config = proxy.production_app()
    assert config.focused_ui is focused
    assert config.production
    assert config.agent == "carrie"
    assert config.prefix == "/carrie"


def test_history_scope_and_secret_redaction(api_client: TestClient, unique_user: TestUser, monkeypatch):
    rpc = AsyncMock(return_value={"messages": []})
    monkeypatch.setattr(CarrieService, "rpc", rpc)
    result = api_client.post(f"{PREFIX}/history", headers=unique_user.token, json=CONTEXT)
    assert result.status_code == 200
    assert unique_user.household_id in rpc.call_args.args[1]["sessionKey"]
    rpc.side_effect = CarrieUnavailable("secret-token raw-gateway-diagnostics")
    result = api_client.post(f"{PREFIX}/history", headers=unique_user.token, json=CONTEXT)
    assert result.status_code == 503
    assert "secret-token" not in result.text


def test_session_isolation(monkeypatch):
    context = CarrieContext.model_validate(CONTEXT)
    first = CarrieService(uuid4())
    second = CarrieService(uuid4())
    key = first.session_key(context)
    assert key != second.session_key(context)
    monkeypatch.setattr(get_app_settings(), "CARRIE_INSTANCE_ID", "another-instance")
    assert key != first.session_key(context)


def test_history_never_exposes_tools_or_reasoning():
    history = CarrieService.normalize_history(
        {
            "messages": [
                {"id": "a", "role": "toolResult", "content": "secret"},
                {
                    "id": "b",
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "private reasoning"},
                        {"type": "text", "text": "The plan has two meals."},
                    ],
                },
                {
                    "id": "c",
                    "role": "user",
                    "content": "[Mealie planner context]\n{}\n[/Mealie planner context]\n\nReview this week",
                },
            ]
        }
    )
    assert [message.text for message in history.messages] == ["The plan has two meals.", "Review this week"]


def test_invalid_date_range():
    with pytest.raises(ValidationError):
        CarrieContext(start_date="2026-11-08", end_date="2026-11-02")


@pytest.mark.asyncio
async def test_send_is_scoped_and_disables_slash_commands(monkeypatch):
    service = CarrieService(UUID("11111111-1111-4111-8111-111111111111"))
    rpc = AsyncMock(return_value={"runId": "run-1"})
    monkeypatch.setattr(service, "rpc", rpc)
    data = CarrieSend.model_validate({**CONTEXT, "message": "/config get", "requestId": str(uuid4())})
    await service.send(data)
    method, params = rpc.call_args.args
    assert method == "chat.send"
    assert params["suppressCommandInterpretation"] is True
    assert params["deliver"] is False
    assert "11111111-1111-4111-8111-111111111111" in params["sessionKey"]
    assert params["idempotencyKey"] != str(data.request_id)
    await service.send(data)
    assert rpc.call_args.args[1]["idempotencyKey"] == params["idempotencyKey"]


def test_gateway_v4_history_state():
    history = CarrieService.normalize_history(
        {
            "messages": [],
            "pendingInputs": None,
            "sessionInfo": {"hasActiveRun": True, "activeLeafEntryId": "leaf-42"},
        }
    )
    assert history.running
    assert history.leaf_entry_id == "leaf-42"


def test_foreign_diner_rejected(api_client: TestClient, unique_user: TestUser, monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(CarrieService, "send", send)
    result = api_client.post(
        f"{PREFIX}/messages",
        headers=unique_user.token,
        json={
            **CONTEXT,
            "message": "Review",
            "requestId": str(uuid4()),
            "dinerIds": [str(uuid4())],
        },
    )
    assert result.status_code == 422
    send.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [False, True])
async def test_protocol_handshake_and_conflict(monkeypatch, caplog, conflict):
    requests = []

    async def gateway(socket):
        await socket.send(json.dumps({"type": "event", "event": "connect.challenge", "payload": {"nonce": "test"}}))
        hello = json.loads(await socket.recv())
        requests.append(hello)
        await socket.send(json.dumps({"type": "res", "id": hello["id"], "ok": True, "payload": {"type": "hello-ok"}}))
        request = json.loads(await socket.recv())
        requests.append(request)
        await socket.send(
            json.dumps(
                {
                    "type": "res",
                    "id": request["id"],
                    "ok": not conflict,
                    "payload": {"runId": "run-42"},
                    "error": {"details": {"reason": "active-leaf-changed"}},
                }
            )
        )

    service = CarrieService(uuid4())
    settings = get_app_settings()
    monkeypatch.setattr(settings, "CARRIE_GATEWAY_TOKEN", "test-secret-never-log")
    monkeypatch.setattr(settings, "CARRIE_HOUSEHOLD_ID", str(service.household_id))
    caplog.set_level(logging.DEBUG)
    async with serve(gateway, "127.0.0.1", 0, logger=logging.getLogger("mealie.carrie.transport")) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setattr(settings, "CARRIE_GATEWAY_URL", f"ws://127.0.0.1:{port}")
        if conflict:
            with pytest.raises(CarrieConflict):
                await service.rpc("chat.send", {"message": "Hello"})
        else:
            assert await service.rpc("chat.send", {"message": "Hello"}) == {"runId": "run-42"}
    assert requests[0]["params"]["minProtocol"] == 4
    assert requests[0]["params"]["scopes"] == ["operator.admin"]
    assert "test-secret-never-log" not in caplog.text
