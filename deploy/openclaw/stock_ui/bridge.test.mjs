import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(new URL("../../../mealie/services/carrie_ui/bridge.js", import.meta.url), "utf8");
const context = { startDate: "2026-11-02", endDate: "2026-11-08", dinerIds: [], includeCooking: true };

function harness(pathname = "/chat/carrie-dev/test", production = false) {
  const sent = [];
  const notifications = [];
  const handlers = {};
  const connections = [];
  const fetches = [];
  class Socket extends EventTarget {
    constructor(url) { super(); connections.push(url); }
    static OPEN = 1;
    readyState = 1;
    send(raw) { sent.push(JSON.parse(raw)); }
  }
  const parent = { postMessage: (data, origin) => notifications.push({ data, origin }) };
  const origin = production ? "https://mealie.example.test" : "http://127.0.0.1:18800";
  const parentOrigin = production ? origin : "http://localhost:3000";
  const location = { pathname, href: `${origin}${pathname}`, origin, host: new URL(origin).host };
  const window = { parent, WebSocket: Socket, addEventListener: (event, callback) => { handlers[event] = callback; }, fetch: async (...args) => { fetches.push(args); } };
  const history = { pushState: (_state, _title, path) => { location.pathname = path; }, replaceState: (_state, _title, path) => { location.pathname = path; } };
  vm.runInNewContext(source, {
    window, history, location, document: { currentScript: { dataset: { parentOrigin, prefix: production ? "/carrie" : "", agent: production ? "carrie" : "carrie-dev" } } },
    crypto: { randomUUID: () => "document-1" }, URL, Headers, Request, MessageEvent, structuredClone, queueMicrotask,
  });
  const socket = new window.WebSocket(origin.replace("http", "ws") + "/");
  const post = (data, origin = parentOrigin, sender = parent) => handlers.message({ origin, source: sender, data: {
    source: "mealie-planner", version: 1, documentId: "document-1", ...data,
  } });
  const rpc = (method, params, id = "request-1") => socket.send(JSON.stringify({ type: "req", id, method, params }));
  return { socket, sent, notifications, post, rpc, history, window, connections, fetches };
}

test("context is explicitly shared with one session and cleared on another", () => {
  const h = harness();
  h.rpc("chat.history", { sessionKey: "agent:carrie-dev:first" });
  h.post({ type: "share", sessionKey: "agent:carrie-dev:first", context, revision: "r1" });
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:first", message: "test" });
  assert.deepEqual(h.sent.at(-1).params.__mealieContext, context);
  h.rpc("chat.history", { sessionKey: "agent:carrie-dev:second" });
  const count = h.sent.length;
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:second", message: "test" });
  assert.equal(h.sent.length, count);
  assert.equal(h.notifications.at(-1).data.type, "context-needed");
});

test("wrong origin, source, document, and session cannot inject context", () => {
  const h = harness();
  h.rpc("chat.history", { sessionKey: "agent:carrie-dev:first" });
  const share = { type: "share", sessionKey: "agent:carrie-dev:first", context };
  h.post(share, "https://evil.example");
  h.post(share, "http://localhost:3000", {});
  h.post({ ...share, documentId: "old-document" });
  h.post({ ...share, sessionKey: "agent:carrie-dev:other" });
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:first", message: "test" });
  assert.equal(h.sent.length, 1);
});

test("new-session prompt carries explicitly shared view", () => {
  const h = harness("/new");
  h.post({ type: "share", sessionKey: "@new", context, revision: "r1" });
  h.rpc("sessions.create", { agentId: "carrie-dev", message: "test" });
  assert.deepEqual(h.sent.at(-1).params.__mealieContext, context);
  h.socket.dispatchEvent(new MessageEvent("message", { data: JSON.stringify({
    type: "res", id: "request-1", ok: true, payload: { key: "agent:carrie-dev:new" },
  }) }));
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:new", message: "followup" });
  assert.deepEqual(h.sent.at(-1).params.__mealieContext, context);
});

test("late creation reply cannot restore context after parent invalidates it", () => {
  const h = harness("/new");
  h.post({ type: "share", sessionKey: "@new", context, revision: "r1" });
  h.rpc("sessions.create", { agentId: "carrie-dev", message: "test" });
  h.post({ type: "clear" });
  h.socket.dispatchEvent(new MessageEvent("message", { data: JSON.stringify({
    type: "res", id: "request-1", ok: true, payload: { key: "agent:carrie-dev:new" },
  }) }));
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:new", message: "followup" });
  assert.equal(h.sent.length, 1);
});

test("tabs keep separate context; New conversation clears prior sharing", () => {
  const a = harness("/new");
  const b = harness("/new");
  a.post({ type: "share", sessionKey: "@new", context });
  b.rpc("sessions.create", { agentId: "carrie-dev", message: "test" });
  assert.equal(b.sent.length, 0);
  a.rpc("chat.history", { sessionKey: "agent:carrie-dev:first" });
  a.post({ type: "share", sessionKey: "agent:carrie-dev:first", context });
  a.history.pushState({}, "", "/new");
  a.rpc("sessions.create", { agentId: "carrie-dev", message: "test" });
  assert.equal(a.sent.length, 1);
});

test("lease is sent in first WebSocket frame, never in URL; remote gateways rejected", async () => {
  const h = harness("/new");
  h.post({ type: "initialize", lease: "fictional-lease" });
  h.socket.dispatchEvent(new Event("open"));
  await Promise.resolve();
  assert.deepEqual(h.sent[0], { type: "mealie-auth", lease: "fictional-lease" });
  assert.throws(() => new h.window.WebSocket("wss://evil.example/"));
});

test("cached deep-linked threads can share without a chat.history request", () => {
  const h = harness("/chat/carrie-dev/first");
  assert.equal(h.notifications[0].data.sessionKey, "@route:/chat/carrie-dev/first");
  h.post({ type: "share", sessionKey: "@route:/chat/carrie-dev/first", context, revision: "r1" });
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:first", message: "test" });
  assert.deepEqual(h.sent.at(-1).params.__mealieContext, context);
  h.history.pushState({}, "", "/chat/carrie-dev/second");
  h.rpc("chat.send", { sessionKey: "agent:carrie-dev:second", message: "test" });
  assert.equal(h.sent.length, 1);
  assert.equal(h.notifications.at(-1).data.type, "context-needed");
});

test("production routes HTTP and WebSocket through the same-origin /carrie mount", async () => {
  const h = harness("/carrie/new", true);
  assert.equal(h.notifications[0].data.sessionKey, "@new");
  assert.equal(h.connections[0], "wss://mealie.example.test/carrie/");
  new h.window.WebSocket("wss://mealie.example.test/carrie");
  assert.equal(h.connections[1], "wss://mealie.example.test/carrie/");
  assert.throws(() => new h.window.WebSocket("wss://mealie.example.test/admin"));
  h.post({ type: "initialize", lease: "fictional-lease" });
  await h.window.fetch("/control-ui-config.json");
  assert.equal(h.fetches[0][0].href, "https://mealie.example.test/carrie/control-ui-config.json");
  assert.equal(h.fetches[0][1].headers.get("X-Mealie-Lease"), "fictional-lease");
  await h.window.fetch("/carrie/control-ui-config.json");
  assert.equal(h.fetches[1][0].pathname, "/carrie/control-ui-config.json");
  h.post({ type: "share", sessionKey: "@new", context });
  h.rpc("sessions.create", { agentId: "carrie", message: "Review this week" });
  assert.deepEqual(h.sent.at(-1).params.__mealieContext, context);
  await assert.rejects(h.window.fetch("https://evil.example/api"));
});
