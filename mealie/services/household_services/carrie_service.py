import asyncio
import hashlib
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from mealie.schema.carrie.chat import CarrieAccepted, CarrieContext, CarrieHistory, CarrieMessage, CarrieSend
from mealie.services._base_service import BaseService

# WebSocket frame debugging includes authentication and conversation contents.
# Keep it disabled even when Mealie's development root logger is at DEBUG.
transport_logger = logging.getLogger("mealie.carrie.transport")
transport_logger.setLevel(logging.WARNING)


class CarrieUnavailable(Exception):
    """Safe public error; never forward Gateway responses, URLs, or credentials."""


class CarrieConflict(Exception):
    pass


class CarrieService(BaseService):
    def __init__(self, household_id: UUID):
        super().__init__()
        self.household_id = household_id

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.CARRIE_GATEWAY_URL
            and self.settings.CARRIE_GATEWAY_TOKEN
            and self.settings.CARRIE_HOUSEHOLD_ID == str(self.household_id)
        )

    def session_key(self, context: CarrieContext) -> str:
        agent = self.settings.CARRIE_AGENT_ID
        if not re.fullmatch(r"[a-z0-9_-]+", agent):
            raise CarrieUnavailable()
        namespace = hashlib.sha256(self.settings.CARRIE_INSTANCE_ID.encode()).hexdigest()[:16]
        return f"agent:{agent}:mealie:{namespace}:{self.household_id}:{context.start_date}:{context.end_date}"

    async def rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise CarrieUnavailable()
        url = self.settings.CARRIE_GATEWAY_URL
        parsed = urlparse(url)
        # Plain WS is intended only for a private tunnel; never accept a target from a request.
        if parsed.scheme not in {"ws", "wss"} or parsed.username or parsed.password:
            raise CarrieUnavailable()
        try:
            async with (
                asyncio.timeout(20),
                connect(url, max_size=2**20, open_timeout=10, proxy=None, logger=transport_logger) as socket,
            ):
                challenge = json.loads(await socket.recv())
                if challenge.get("event") != "connect.challenge":
                    raise CarrieUnavailable()
                connect_id = str(uuid4())
                await socket.send(
                    json.dumps(
                        {
                            "type": "req",
                            "id": connect_id,
                            "method": "connect",
                            "params": {
                                "minProtocol": self.settings.CARRIE_PROTOCOL_VERSION,
                                "maxProtocol": self.settings.CARRIE_PROTOCOL_VERSION,
                                "client": {
                                    "id": "gateway-client",
                                    "version": "1.0.0",
                                    "platform": "linux",
                                    "mode": "backend",
                                },
                                "role": "operator",
                                # Protocol v4 requires admin scope to suppress slash commands.
                                # Only this fixed backend adapter ever receives the credential.
                                "scopes": ["operator.admin"]
                                if method == "chat.send"
                                else ["operator.read", "operator.write"],
                                "auth": {"token": self.settings.CARRIE_GATEWAY_TOKEN},
                            },
                        }
                    )
                )
                request_id = str(uuid4())
                while True:
                    frame = json.loads(await socket.recv())
                    if frame.get("type") != "res":
                        continue
                    if frame.get("id") == connect_id:
                        if not frame.get("ok"):
                            raise CarrieUnavailable()
                        await socket.send(
                            json.dumps({"type": "req", "id": request_id, "method": method, "params": params})
                        )
                    elif frame.get("id") == request_id:
                        if not frame.get("ok"):
                            # Diagnostics stay with OpenClaw; user-facing responses are deliberately bounded.
                            details = (frame.get("error") or {}).get("details") or {}
                            if details.get("reason") in {"active-leaf-changed", "session-settings-changed"}:
                                raise CarrieConflict()
                            raise CarrieUnavailable()
                        payload = frame.get("payload")
                        if not isinstance(payload, dict):
                            raise CarrieUnavailable()
                        return payload
        except (TimeoutError, OSError, WebSocketException, ValueError, TypeError) as error:
            raise CarrieUnavailable() from error

    async def raw_history(self, context: CarrieContext) -> dict[str, Any]:
        return await self.rpc(
            "chat.history", {"sessionKey": self.session_key(context), "limit": 100, "maxBytes": 500_000}
        )

    async def history(self, context: CarrieContext) -> CarrieHistory:
        return self.normalize_history(await self.raw_history(context))

    @staticmethod
    def normalize_history(payload: dict[str, Any]) -> CarrieHistory:
        messages = []
        for index, message in enumerate(payload.get("messages", [])):
            role = message.get("role")
            if role not in {"user", "assistant"} or message.get("isReasoning"):
                continue
            content = message.get("content", [])
            text = (
                content
                if isinstance(content, str)
                else "\n".join(
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text" and not block.get("isReasoning")
                )
            )
            if role == "user" and text.startswith("[Mealie planner context]\n"):
                text = text.partition("\n[/Mealie planner context]\n\n")[2]
            if text.strip():
                messages.append(CarrieMessage(id=str(message.get("id", index)), role=role, text=text))
        session_info = payload.get("sessionInfo") or {}
        return CarrieHistory(
            messages=messages,
            running=bool(
                session_info.get("hasActiveRun")
                or payload.get("inFlightRun")
                or (payload.get("pendingInputs") or {}).get("items")
            ),
            leaf_entry_id=session_info.get("activeLeafEntryId"),
            truncated=bool(payload.get("hasMore") or payload.get("nextCursor")),
        )

    async def send(self, data: CarrieSend) -> CarrieAccepted:
        # Let the Gateway atomically check the leaf and deduplicate retries. A local
        # precheck would reject a retry whose original message already advanced it.
        context = data.model_dump(mode="json", include={"start_date", "end_date", "diner_ids", "include_cooking"})
        message = (
            "[Mealie planner context]\n"
            + json.dumps(context)
            + "\n[/Mealie planner context]\n\n"
            + data.message.strip()
        )
        if not data.message.strip():
            raise ValueError("Message cannot be blank")
        # Keep retries scoped to this household and conversation, even if the same UUID is reused elsewhere.
        identity = hashlib.sha256(f"{self.session_key(data)}:{data.request_id}".encode()).hexdigest()
        params: dict[str, Any] = {
            "sessionKey": self.session_key(data),
            "message": message,
            "idempotencyKey": identity,
            "deliver": False,
            "suppressCommandInterpretation": True,
            "expectedLeafEntryId": data.expected_leaf_entry_id,
        }
        result = await self.rpc("chat.send", params)
        if not isinstance(result.get("runId"), str):
            raise CarrieUnavailable()
        return CarrieAccepted(run_id=result["runId"])

    async def stop(self, context: CarrieContext) -> None:
        await self.rpc("chat.abort", {"sessionKey": self.session_key(context)})
