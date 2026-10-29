"""Authenticated, narrowly scoped host for a dedicated Carrie's stock UI."""

import asyncio
import ipaddress
import json
import logging
import os
import re
import secrets
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date
from pathlib import Path
from typing import Self
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from websockets.asyncio.client import connect


class PlannerContext(BaseModel):
    """Adapter wire contract; deliberately independent of Mealie/DB startup."""

    model_config = ConfigDict(extra="forbid")
    startDate: date
    endDate: date
    dinerIds: list[UUID] = Field(default_factory=list, max_length=50)
    includeCooking: bool = True

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        if not 0 <= (self.endDate - self.startDate).days <= 62:
            raise ValueError("Choose at most 63 days")
        return self


SCOPES = ["operator.sessions.read", "operator.sessions.write"]
FOCUSED_UI_BUILD = (
    "2026.10.8-release-dc2523e5a5c7-2026-10-27T05-21-21.733Z-"
    "010f999991d275831f307093b3a46cdd2dda1bdd04a84c0c48319b2e2157fda6"
)
TRANSPORT_LOG = logging.getLogger("carrie.stock.transport")
TRANSPORT_LOG.setLevel(logging.WARNING)


@dataclass(frozen=True)
class Config:
    household_id: str
    parent_origin: str = "http://localhost:3000"
    origin: str = "http://127.0.0.1:18800"
    gateway: str = "http://127.0.0.1:18793"
    mealie: str = "http://127.0.0.1:9000"
    agent: str = "carrie-dev"
    lease_seconds: int = 1800
    production: bool = False
    prefix: str = ""
    identity: str = "mealie-dev"
    focused_ui: bool = False

    def __post_init__(self) -> None:
        if self.production:
            public = urlsplit(self.origin)
            if (
                public.scheme != "https"
                or not public.hostname
                or public.username
                or public.password
                or public.path
                or public.query
                or public.fragment
                or public.netloc != public.hostname + (f":{public.port}" if public.port is not None else "")
                or self.parent_origin != self.origin
                or self.prefix != "/carrie"
            ):
                raise ValueError("Production requires one exact HTTPS origin and /carrie prefix")
            for target in (self.gateway, self.mealie):
                parsed = urlsplit(target)
                if (
                    parsed.scheme != "http"
                    or not parsed.hostname
                    or parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                    or parsed.netloc != parsed.hostname + (f":{parsed.port}" if parsed.port is not None else "")
                    or not ipaddress.ip_address(parsed.hostname or "").is_private
                ):
                    raise ValueError("Upstreams must be explicitly configured private IP HTTP origins")
            if not self.household_id or not re.fullmatch(r"[a-z0-9_-]+", self.agent):
                raise ValueError("A dedicated agent and household are required")
            return
        for origin in (self.parent_origin, self.origin, self.gateway, self.mealie):
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"localhost", "127.0.0.1"}
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.netloc != parsed.hostname + (f":{parsed.port}" if parsed.port is not None else "")
            ):
                raise ValueError("This experiment only supports exact loopback HTTP origins")
        if self.origin == self.parent_origin or not self.household_id:
            raise ValueError("Use a separate origin and an explicit development household")
        if self.agent != "carrie-dev":
            raise ValueError("This experiment is restricted to carrie-dev")


@dataclass
class Lease:
    bearer: str
    expires: float
    sockets: int = 0
    requests: list[float] = dataclass_field(default_factory=list)


def gateway_headers(config: Config) -> dict[str, str]:
    # The dedicated Gateway trusts only our explicitly configured proxy peer.
    # This documentation-range address is synthetic, NOT a real client IP.
    # Never copy browser-supplied forwarding, auth, cookie, or identity headers.
    return {
        "x-forwarded-for": "192.0.2.1",
        "x-forwarded-proto": urlsplit(config.origin).scheme,
        "x-forwarded-host": urlsplit(config.origin).netloc,
        "x-mealie-user": config.identity,
        "x-openclaw-scopes": ",".join(SCOPES),
    }


def annotate_send(frame: dict, agent: str) -> dict:
    """Consume our private transport envelope; never send it as an RPC field."""
    params = dict(frame.get("params") or {})
    context = PlannerContext.model_validate(params.pop("__mealieContext", None))
    creating = frame.get("method") == "sessions.create"
    if creating:
        if params.get("agentId") != agent:
            raise ValueError("Wrong agent")
    else:
        session_key = params.get("sessionKey", "")
        if not isinstance(session_key, str) or not session_key.startswith(f"agent:{agent}:"):
            raise ValueError("Wrong agent")
    message_field = "task" if creating and "task" in params else "message"
    message = params.get(message_field)
    if creating and message is None:
        return {**frame, "params": params}
    if not isinstance(message, str) or not message.strip() or len(message) > 8000:
        raise ValueError("Invalid message")
    # Command execution is not part of the meal-planning proof of concept.
    # Prefixing prevents ordinary slash interpretation without requesting admin.
    params[message_field] = (
        "[Mealie planner context — current view for this message]\n"
        + context.model_dump_json(by_alias=True)
        + "\n[/Mealie planner context]\n\n"
        + message
    )
    if not creating:
        params["deliver"] = False
    return {**frame, "params": params}


def constrain_request(frame: dict) -> None:
    """Additional PoC limits; Gateway scopes/ownership remain authoritative."""
    method = frame.get("method", "")
    params = frame.get("params") or {}
    mutations = {"connect", "chat.send", "chat.abort", "sessions.create", "sessions.patch", "sessions.abort"}
    reads = {
        "agents.list",
        "agent.identity.get",
        "models.list",
        "users.self",
        "chat.history",
        # Stock UI deep links resolve the thread and read its transcript together.
        "chat.startup",
        "sessions.list",
        "sessions.get",
        "sessions.resolve",
        "sessions.preview",
        "sessions.describe",
        "sessions.search",
        "sessions.subscribe",
        "sessions.unsubscribe",
        "sessions.messages.subscribe",
        "sessions.messages.unsubscribe",
    }
    if not isinstance(method, str) or method not in mutations | reads:
        raise ValueError("This action is outside the chat prototype")
    if method == "connect":
        return  # Preserve the stock UI's signed device payload intact.
    if not isinstance(params, dict):
        raise ValueError("Expected parameters")
    for field in (
        "toolOverrides",
        "execNode",
        "cwd",
        "projectId",
        "projectGitUrl",
        "repository",
        "worktree",
        "incognito",
        "attachments",
        "mentions",
        "fork",
        "parentSessionKey",
        "emitCommandHooks",
        "succeedsParent",
        "permissionMode",
        "sandboxMode",
        "nativeRuntimeConsent",
    ):
        if params.get(field) not in (None, False, [], {}):
            raise ValueError("Execution, attachments, and workspace changes are not part of this prototype")
    if params.get("agentRuntime") not in (None, "openclaw"):
        raise ValueError("Embedded runtime only")
    # Match the dedicated Gateway's configured model. Do not let the picker
    # select arbitrary provider/runtime combinations via a crafted request.
    if params.get("model") not in (None, "", "openai/gpt-5.6-sol"):
        raise ValueError("Model is not configured for Carrie")
    if method == "sessions.patch":
        allowed = {
            "key",
            "agentId",
            "expectedSessionId",
            "expectedLifecycleRevision",
            "label",
            "autoLabel",
            "icon",
            "color",
            "category",
            "archived",
            "pinned",
            "unread",
            "expectedMarkedUnreadAt",
            "thinkingLevel",
            "model",
            "agentRuntime",
            "fastMode",
            "reasoningLevel",
            "verboseLevel",
        }
        if set(params) - allowed:
            raise ValueError("Only conversation organization and chat settings are supported")


def embed_html(body: str, config: Config) -> str:
    import html

    presentation = ""
    if config.focused_ui:
        # Native embed is a versioned host contract, not a general web UI SDK.
        if f'data-openclaw-control-ui-build-id="{FOCUSED_UI_BUILD}"' not in body:
            raise ValueError("Untested stock conversation UI build")
        body = body.replace("<html ", '<html data-mealie-chat="loading" ', 1)
        presentation = (
            f'<link rel="stylesheet" href="{config.prefix}/__mealie__/conversation.css">'
            f'<script src="{config.prefix}/__mealie__/conversation.js" '
            f'data-prefix="{config.prefix}" data-agent="{config.agent}"></script>'
        )
    tag = (
        f'<script src="{config.prefix}/__mealie__/bridge.js" '
        f'data-parent-origin="{html.escape(config.parent_origin, quote=True)}" '
        f'data-prefix="{config.prefix}" data-agent="{config.agent}"></script>'
    )
    if "<head>" not in body:
        raise ValueError("Unrecognized stock UI shell")
    return body.replace("<head>", "<head>" + presentation + tag, 1)


def create_app(config: Config, client: httpx.AsyncClient | None = None) -> FastAPI:  # noqa: C901
    # Route-local closures keep the per-instance lease store private; complexity
    # here counts all separately tested route handlers, not one decision tree.
    leases: dict[str, Lease] = {}
    logins: list[float] = []
    http = client or httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            leases.clear()
            if client is None:
                await http.aclose()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.http = http
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[config.parent_origin],
        allow_credentials=True,
        allow_methods=["POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Mealie-Lease"],
    )

    @app.middleware("http")
    async def enforce_host(request: Request, call_next):
        if request.headers.get("host") != urlsplit(config.origin).netloc:
            return Response(status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    async def authenticate(bearer: str) -> None:
        if not bearer.startswith("Bearer ") or len(bearer) > 8192:
            raise HTTPException(401, "Sign into Mealie first")
        try:
            result = await http.get(config.mealie + "/api/users/self", headers={"Authorization": bearer, "Cookie": ""})
            user = result.json() if result.status_code == 200 else {}
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, "Mealie authentication unavailable") from None
        if user.get("householdId") != config.household_id:
            raise HTTPException(403, "Configured household access required")

    def lease_for(key: str) -> Lease:
        lease = leases.get(key)
        if lease is None or lease.expires <= time.monotonic():
            leases.pop(key, None)
            raise HTTPException(401, "Reopen Carrie from Mealie")
        return lease

    def require_parent(request: Request) -> None:
        if request.headers.get("origin") != config.parent_origin:
            raise HTTPException(403, "Mealie origin required")

    @app.post("/__mealie__/auth")
    async def login(request: Request):
        require_parent(request)
        now = time.monotonic()
        logins[:] = [t for t in logins if t > now - 60]
        if len(logins) >= 30:
            raise HTTPException(429, "Too many authentication requests")
        logins.append(now)
        bearer = request.headers.get("authorization", "")
        await authenticate(bearer)
        for key in list(leases):
            if leases[key].expires <= time.monotonic():
                leases.pop(key)
        if len(leases) >= 64:
            raise HTTPException(429, "Too many sessions")
        key = secrets.token_urlsafe(32)
        leases[key] = Lease(bearer, time.monotonic() + config.lease_seconds)
        response = JSONResponse({"lease": key})
        if config.production:
            # Shell/asset access only. RPC leases remain per-panel, not global
            # cookies, so two tabs cannot exchange their planner context.
            response.set_cookie(
                "__Secure-mealie-carrie-ui",
                key,
                max_age=config.lease_seconds,
                secure=True,
                httponly=True,
                samesite="strict",
                path=config.prefix + "/",
            )
        return response

    @app.delete("/__mealie__/auth")
    async def logout(request: Request):
        require_parent(request)
        leases.pop(request.headers.get("x-mealie-lease", ""), None)
        return Response(status_code=204)

    @app.get("/__mealie__/bridge.js")
    async def bridge(request: Request):
        if config.production:
            lease_for(request.cookies.get("__Secure-mealie-carrie-ui", ""))
        return FileResponse(Path(__file__).with_name("bridge.js"), media_type="text/javascript")

    @app.get("/__mealie__/{asset}")
    async def presentation_asset(request: Request, asset: str):
        if not config.focused_ui or asset not in {"conversation.js", "conversation.css"}:
            raise HTTPException(404)
        if config.production:
            lease_for(request.cookies.get("__Secure-mealie-carrie-ui", ""))
        return FileResponse(
            Path(__file__).with_name(asset),
            media_type="text/javascript" if asset.endswith(".js") else "text/css",
        )

    @app.get("/{path:path}")
    async def stock(request: Request, path: str):
        if config.focused_ui and (
            path.startswith("chat/")
            and not path.startswith(f"chat/{config.agent}/")
            or path == "new"
            and request.query_params.get("agent", config.agent) != config.agent
        ):
            raise HTTPException(404)
        # Public shell/assets contain no user data. Dynamic fetches receive a
        # per-frame lease via the injected bridge, not cookies or URL credentials.
        public = path in {
            "",
            "new",
            "favicon.ico",
            "favicon.svg",
            "favicon-32.png",
            "apple-touch-icon.png",
            "manifest.webmanifest",
        } or path.startswith(("assets/", "fonts/", "themes/", "file-icons/", "provider-icons/", "app-art/", "chat/"))
        # Even anonymous static requests from a trusted proxy peer must identify
        # the originating client. Do not attach identity/scopes to these assets.
        headers_in = {
            **{key: value for key, value in gateway_headers(config).items() if key.startswith("x-forwarded-")},
            "Accept": request.headers.get("accept", "*/*"),
            "Cookie": "",
        }
        if public and config.production:
            shell_lease = lease_for(
                request.headers.get("x-mealie-lease", "") or request.cookies.get("__Secure-mealie-carrie-ui", "")
            )
            if path in {"", "new"} or path.startswith("chat/"):
                await authenticate(shell_lease.bearer)
        if not public:
            lease_for(request.headers.get("x-mealie-lease", ""))
            if path not in {
                "control-ui-config.json",
                "__openclaw__/control-ui-config.json",
                "__openclaw__/session-entry",
            }:
                raise HTTPException(404)
            headers_in.update(gateway_headers(config))
        # No arbitrary upstream URL, redirects, service worker, file API, or uploads.
        if (
            path == "sw.js"
            or ".." in path
            or "\\" in path
            or path.startswith(("api/", "tools/", "v1/"))
            or request.url.query
            and path.startswith("__mealie__/")
        ):
            raise HTTPException(404)
        try:
            # Gateway deep links may return its login page before browser auth.
            # Serve the public SPA shell; its router still sees the original
            # /chat/... URL and loads history over the authenticated WebSocket.
            upstream_path = "new" if path.startswith("chat/") else path
            result = await http.get(
                config.gateway + config.prefix + "/" + upstream_path,
                params=request.query_params,
                headers=headers_in,
            )
        except httpx.HTTPError:
            raise HTTPException(503, "Carrie Gateway unavailable") from None
        if result.is_redirect:
            raise HTTPException(502, "Unexpected Gateway redirect")
        headers = {
            key: value
            for key, value in result.headers.items()
            if key.lower() in {"content-type", "content-security-policy"}
        }
        body = result.content
        if "text/html" in headers.get("content-type", ""):
            try:
                body = embed_html(result.text, config).encode()
            except ValueError:
                raise HTTPException(502, "Unrecognized stock UI version") from None
            csp = headers.get("content-security-policy", "")
            if "frame-ancestors 'none'" not in csp:
                raise HTTPException(502, "Unrecognized stock UI framing policy")
            headers["content-security-policy"] = csp.replace(
                "frame-ancestors 'none'", f"frame-ancestors {config.parent_origin}"
            )
        return Response(body, status_code=result.status_code, headers=headers)

    @app.websocket("/")
    async def websocket(browser: WebSocket):  # noqa: C901 - bounded bidirectional transport and cleanup
        if (
            browser.headers.get("host") != urlsplit(config.origin).netloc
            or browser.headers.get("origin") != config.origin
        ):
            await browser.close(code=1008)
            return
        await browser.accept()
        lease: Lease | None = None
        counted = False
        try:
            async with asyncio.timeout(15):
                first = await browser.receive_json()
            if not isinstance(first, dict) or first.get("type") != "mealie-auth":
                raise ValueError("Expected Mealie lease")
            key = first.get("lease", "")
            if not isinstance(key, str):
                raise ValueError("Invalid lease")
            lease = lease_for(key)
            await authenticate(lease.bearer)
            if lease.sockets >= 2 or sum(item.sockets for item in leases.values()) >= 32:
                raise ValueError("Too many connections")
            lease.sockets += 1
            counted = True
            async with connect(
                config.gateway.replace("http://", "ws://", 1) + config.prefix + "/",
                additional_headers=gateway_headers(config),
                origin=config.origin,
                max_size=2**22,
                proxy=None,
                logger=TRANSPORT_LOG,
            ) as gateway:

                async def to_gateway():
                    while True:
                        raw = await browser.receive_text()
                        if len(raw) > 128_000:
                            raise ValueError("Oversized request")
                        frame = json.loads(raw)
                        if not isinstance(frame, dict) or frame.get("type") != "req":
                            raise ValueError("Expected RPC request")
                        lease_for(key)
                        try:
                            constrain_request(frame)
                            params = frame.get("params") or {}
                            for name in ("agentId", "sessionKey", "key"):
                                value = params.get(name)
                                if name == "agentId" and value and value != config.agent:
                                    raise ValueError("Wrong agent")
                                if (
                                    isinstance(value, str)
                                    and value.startswith("agent:")
                                    and not value.startswith(f"agent:{config.agent}:")
                                ):
                                    raise ValueError("Wrong agent")
                            if frame.get("method") in {"chat.send", "sessions.create"}:
                                now = time.monotonic()
                                lease.requests[:] = [t for t in lease.requests if t > now - 60]
                                if len(lease.requests) >= 10:
                                    raise ValueError("Too many messages")
                                lease.requests.append(now)
                                await authenticate(lease.bearer)
                                frame = annotate_send(frame, config.agent)
                        except (HTTPException, ValidationError, ValueError):
                            await browser.send_json(
                                {
                                    "type": "res",
                                    "id": frame.get("id"),
                                    "ok": False,
                                    "error": {
                                        "code": "INVALID_REQUEST",
                                        "message": (
                                            "This panel supports plain chat and thread organization only. "
                                            "Wait for the current Mealie view to connect before sending."
                                        ),
                                    },
                                }
                            )
                            continue
                        await gateway.send(json.dumps(frame))

                async def to_browser():
                    async for raw in gateway:
                        lease_for(key)
                        result = json.loads(raw)
                        payload = result.get("payload") or {}
                        if payload.get("type") == "hello-ok":
                            granted = payload.get("auth", {}).get("scopes", [])
                            if set(granted) - set(SCOPES):
                                raise ValueError("Unexpected Gateway permissions")
                        await browser.send_text(raw if isinstance(raw, str) else raw.decode())

                tasks = [asyncio.create_task(to_gateway()), asyncio.create_task(to_browser())]
                next_auth = time.monotonic() + 60
                try:
                    # Also expire idle sockets and revoked leases without waiting for traffic.
                    while not any(task.done() for task in tasks):
                        lease_for(key)
                        if time.monotonic() >= next_auth:
                            await authenticate(lease.bearer)
                            next_auth = time.monotonic() + 60
                        await asyncio.wait(tasks, timeout=1, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            # No raw Gateway frames, credentials, messages, or exception repr in logs.
            pass
        finally:
            if lease is not None and counted:
                lease.sockets = max(0, lease.sockets - 1)
            try:
                await browser.close(code=1000)
            except (RuntimeError, WebSocketDisconnect):
                pass

    return app


def app_factory() -> FastAPI:
    if os.environ.get("CARRIE_STOCK_DEV") != "1":
        raise RuntimeError("Set CARRIE_STOCK_DEV=1 to enable this development-only experiment")
    return create_app(
        Config(
            household_id=os.environ["CARRIE_HOUSEHOLD_ID"],
            focused_ui=os.environ.get("CARRIE_STOCK_FOCUSED_UI") == "1",
        )
    )


def production_app() -> FastAPI:
    from mealie.core.config import get_app_settings

    settings = get_app_settings()
    return create_app(
        Config(
            household_id=settings.CARRIE_HOUSEHOLD_ID,
            parent_origin=settings.CARRIE_STOCK_PUBLIC_ORIGIN,
            origin=settings.CARRIE_STOCK_PUBLIC_ORIGIN,
            gateway=settings.CARRIE_STOCK_GATEWAY_URL,
            mealie=f"http://127.0.0.1:{settings.API_PORT}",
            agent=settings.CARRIE_AGENT_ID,
            identity="mealie",
            production=True,
            prefix="/carrie",
            focused_ui=settings.CARRIE_STOCK_FOCUSED_UI,
        )
    )
