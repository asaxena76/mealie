import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import test from "node:test";

const source = fs.readFileSync(new URL("../../../mealie/services/carrie_ui/conversation.js", import.meta.url), "utf8");

function harness() {
  const commands = [];
  const handlers = {};
  const timers = [];
  const nodes = [];
  let nextId = 0;
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.value = ""; nodes.push(this); }
    setAttribute(key, value) { this[key] = value; }
    addEventListener(type, listener) { this.listeners[type] = listener; }
    append(...children) { this.children.push(...children); }
    prepend(child) { this.children.unshift(child); }
    add(option) { this.children.push(option); }
    replaceChildren(...children) { this.children = children; }
  }
  const document = {
    currentScript: { dataset: { prefix: "/carrie", agent: "carrie" } },
    documentElement: { dataset: {} }, body: new Element("body"),
    createElement: tag => new Element(tag),
    addEventListener: (type, listener) => { handlers[type] = listener; },
  };
  const window = {
    dispatchEvent: event => commands.push(event.detail),
    addEventListener: (type, listener) => { handlers[type] = listener; },
  };
  const location = { origin: "https://mealie.example.test", href: "https://mealie.example.test/carrie/new", assign: value => { location.assigned = value; } };
  vm.runInNewContext(source, {
    window, document, location, URL,
    crypto: { randomUUID: () => `request-${++nextId}` },
    CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
    setTimeout: callback => timers.push(callback),
  });
  handlers.DOMContentLoaded();
  const post = message => window.webkit.messageHandlers.openclawConversation.postMessage({ contract: 1, documentId: "doc-1", ...message });
  const ready = () => { window.__OPENCLAW_NATIVE_CONVERSATION_DOCUMENT__ = { contract: 1, documentId: "doc-1" }; return post({ type: "ready", surface: "conversation", capabilities: ["navigate"] }); };
  return { window, document, commands, handlers, timers, nodes, post, ready, location, host: window.__MEALIE_CONVERSATION_HOST__ };
}

test("native contract readiness is document-bound and unavailable fails closed", async () => {
  const h = harness();
  assert.equal(h.window.__OPENCLAW_NATIVE_EMBED__.surface, "conversation");
  assert.equal(h.document.documentElement.dataset.mealieChat, "loading");
  assert.equal((await h.post({ type: "ready" })).ok, false);
  h.timers[0]();
  assert.equal(h.document.documentElement.dataset.mealieChat, "unavailable");
  assert.equal((await h.ready()).ok, true);
  assert.equal(h.document.documentElement.dataset.mealieChat, "ready");
  assert.equal(h.commands[0].type, "presentation");
  assert.equal((await h.post({ type: "ready", documentId: "old-doc" })).ok, false);
  assert.equal((await h.post({ type: "ready", surface: "settings" })).ok, false);
});

test("dashboard handoffs, other agents and stale state are rejected", async () => {
  const h = harness();
  await h.ready();
  assert.equal((await h.post({ type: "open-dashboard", path: "/settings" })).ok, false);
  assert.equal(h.location.assigned, undefined);
  const state = { type: "state", revision: 1, connection: "connected", context: { agentId: "carrie", sessionKey: "agent:carrie:one" } };
  assert.equal((await h.post(state)).ok, true);
  assert.equal((await h.post(state)).ok, false);
  assert.equal((await h.post({ ...state, revision: 2, context: { agentId: "private", sessionKey: "agent:private:one" } })).ok, false);
  assert.equal((await h.post({ type: "route-changed", agentId: "private", sessionKey: "agent:private:one" })).ok, false);
});

test("only Carrie routes are allowed, including same-origin and query checks", () => {
  const { host } = harness();
  for (const path of ["/carrie/new?agent=carrie", "/carrie/chat/carrie/one", "https://mealie.example.test/carrie/chat/carrie/two"]) assert.equal(host.allowedRoute(path), true);
  for (const path of ["/settings", "/carrie/settings", "/carrie/new?agent=private", "/carrie/chat/private/one", "https://evil.example/carrie/chat/carrie/one"]) assert.equal(host.allowedRoute(path), false);
});

test("thread picker filters agents, treats titles as text and navigates via native commands", async () => {
  const h = harness();
  await h.ready();
  let reads = 0;
  h.host.connected(() => reads++);
  h.host.threads([
    { key: "agent:carrie:one", agentId: "carrie", label: "<img src=x>" },
    { key: "agent:private:secret", label: "Private" },
    { key: "agent:carrie:two", agentId: "private", label: "Mismatched" },
  ]);
  const list = h.nodes.find(node => node.tag === "select");
  assert.equal(list.children.length, 2);
  assert.equal(list.children[1].text, "<img src=x>");
  list.value = "agent:carrie:one";
  list.listeners.change();
  assert.equal(h.commands.at(-1).type, "navigate");
  assert.equal(h.commands.at(-1).payload.sessionKey, "agent:carrie:one");
  const result = { type: "command-result", requestId: h.commands.at(-1).requestId, ok: true };
  assert.equal((await h.post(result)).ok, true);
  assert.equal((await h.post(result)).ok, false);
  await h.post({ type: "state", revision: 1, connection: "connected", context: { agentId: "carrie", sessionKey: "agent:carrie:one" } });
  assert.equal(reads, 2);
  h.nodes.find(node => node.textContent === "New conversation").listeners.click();
  assert.equal(h.location.assigned, "/carrie/new?agent=carrie");
});

test("dashboard shortcuts are suppressed but editing and sending are not", () => {
  const h = harness();
  const key = (key, modifiers = {}) => {
    let prevented = false;
    h.handlers.keydown({ key, ...modifiers, preventDefault: () => { prevented = true; }, stopImmediatePropagation() {} });
    return prevented;
  };
  assert.equal(key("k", { metaKey: true }), true);
  assert.equal(key(",", { ctrlKey: true }), true);
  assert.equal(key("S", { metaKey: true, shiftKey: true }), true);
  assert.equal(key("Enter"), false);
  assert.equal(key("c", { metaKey: true }), false);
});
