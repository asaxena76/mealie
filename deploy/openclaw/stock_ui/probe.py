"""Read-only authorization smoke test against ONLY the isolated forwarded Gateway."""

import asyncio
import json

from websockets.asyncio.client import connect

from deploy.openclaw.stock_ui.proxy import SCOPES, Config, gateway_headers


async def main() -> None:
    config = Config("probe")
    async with connect(
        "ws://127.0.0.1:18793", origin=config.origin, additional_headers=gateway_headers(config), proxy=None
    ) as socket:
        await socket.recv()
        await socket.send(
            json.dumps(
                {
                    "type": "req",
                    "id": "connect",
                    "method": "connect",
                    "params": {
                        "minProtocol": 4,
                        "maxProtocol": 4,
                        "client": {"id": "gateway-client", "version": "1.0.0", "platform": "linux", "mode": "backend"},
                        "role": "operator",
                        "scopes": SCOPES,
                    },
                }
            )
        )
        methods = [("agents.list", {}), ("sessions.list", {}), ("config.get", {}), ("tools.invoke", {})]
        replies = {}
        async with asyncio.timeout(20):
            while len(replies) < len(methods):
                result = json.loads(await socket.recv())
                if result.get("type") != "res":
                    continue
                if result["id"] == "connect":
                    if not result.get("ok"):
                        raise RuntimeError("Isolated Gateway connection failed")
                    print("Scopes:", result["payload"]["auth"]["scopes"])  # noqa: T201 - CLI result, no credentials
                    for method, params in methods:
                        await socket.send(json.dumps({"type": "req", "id": method, "method": method, "params": params}))
                else:
                    replies[result["id"]] = result.get("ok")
                    print(result["id"], "allowed" if result.get("ok") else "denied")  # noqa: T201 - CLI result
        assert replies == {"agents.list": True, "sessions.list": True, "config.get": False, "tools.invoke": False}


if __name__ == "__main__":
    asyncio.run(main())
