// Small transport adapter around the UNMODIFIED stock UI. No transcript/DOM scraping.
// Deliberately not a general RPC bridge: the parent can only share/clear view context.
(() => {
  const parentOrigin = document.currentScript.dataset.parentOrigin;
  const prefix = document.currentScript.dataset.prefix || "";
  const agent = document.currentScript.dataset.agent || "carrie-dev";
  const path = () => location.pathname.slice(prefix.length);
  const documentId = crypto.randomUUID();
  const routeSession = () => path() === "/new" ? "@new"
    : path().startsWith(`/chat/${agent}/`) ? `@route:${location.pathname}` : null;
  let sessionKey = routeSession();
  let lastPath = location.pathname;
  let shared = null;
  let revision = null;
  let contextVersion = 0;
  const creations = new Map();
  let resolveLease;
  const leaseReady = new Promise(resolve => { resolveLease = resolve; });
  const stockFetch = window.fetch;
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === "string" ? input : input.url ?? input, location.href);
    if (url.origin !== location.origin) throw new Error("Carrie origin only");
    if (prefix && !url.pathname.startsWith(`${prefix}/`)) url.pathname = prefix + url.pathname;
    const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined));
    headers.set("X-Mealie-Lease", await leaseReady);
    return stockFetch(input instanceof Request ? new Request(url, input) : url, { ...init, headers, credentials: "omit" });
  };
  const notify = (type, extra = {}) => window.parent.postMessage({
    source: "mealie-stock-ui", version: 1, documentId, type, sessionKey, path: location.pathname, ...extra,
  }, parentOrigin);
  const selectSession = (key) => {
    if (typeof key !== "string" || key === sessionKey) return;
    sessionKey = key;
    shared = null;
    contextVersion++;
    notify("session");
  };
  window.addEventListener("message", (event) => {
    if (event.origin !== parentOrigin || event.source !== window.parent) return;
    const data = event.data;
    if (!data || data.source !== "mealie-planner" || data.version !== 1 || data.documentId !== documentId) return;
    if (data.type === "initialize" && typeof data.lease === "string") resolveLease(data.lease);
    if (data.type === "clear") {
      shared = null;
      contextVersion++;
      notify("cleared");
    }
    if (data.type === "share" && sessionKey && data.sessionKey === sessionKey) {
      shared = structuredClone(data.context);
      contextVersion++;
      revision = data.revision;
      notify("shared", { revision: data.revision });
    }
  });
  const StockWebSocket = window.WebSocket;
  window.WebSocket = class extends StockWebSocket {
    constructor(url, protocols) {
      // The experiment never connects to a browser-selected remote Gateway.
      const target = new URL(url, location.href);
      if (target.host !== location.host || !["/", prefix, `${prefix}/`].includes(target.pathname)) throw new Error("Carrie Gateway only");
      target.pathname = `${prefix}/`;
      target.search = "";
      super(target.href, protocols);
      this.addEventListener("open", async () => {
        const lease = await leaseReady;
        if (this.readyState === StockWebSocket.OPEN) super.send(JSON.stringify({ type: "mealie-auth", lease }));
      });
      this.addEventListener("message", (event) => {
        let frame;
        try { frame = JSON.parse(event.data); } catch { return; }
        if (frame.type === "res" && frame.ok && frame.payload?.type === "hello-ok") {
          window.__MEALIE_CONVERSATION_HOST__?.connected(() => super.send(JSON.stringify({
            type: "req", id: "mealie-conversation-list", method: "sessions.list",
            params: { agentId: agent, limit: 100, includeDerivedTitles: true },
          })));
        }
        if (frame.type === "res" && frame.id === "mealie-conversation-list") {
          if (frame.ok) window.__MEALIE_CONVERSATION_HOST__?.threads(frame.payload?.sessions);
          else window.__MEALIE_CONVERSATION_HOST__?.threadsError();
        }
        const context = creations.get(frame.id);
        if (frame.type !== "res" || !context) return;
        creations.delete(frame.id);
        if (!frame.ok || sessionKey !== "@new" || context.version !== contextVersion) return;
        const key = frame.payload?.key ?? frame.payload?.sessionKey ?? frame.payload?.session?.key;
        if (typeof key === "string") {
          sessionKey = key;
          shared = context.value;
          revision = context.revision;
          notify("shared", { revision });
        }
      });
    }
    send(raw) {
      let frame;
      try { frame = JSON.parse(raw); } catch { return super.send(raw); }
      if (frame.type === "req" && frame.method === "chat.history") selectSession(frame.params?.sessionKey);
      if (frame.type === "req" && ["chat.send", "sessions.create"].includes(frame.method)) {
        if (frame.method === "chat.send") {
          // Cached stock threads need not issue chat.history. Bind the explicit
          // visible-route share to the stock composer's first concrete target.
          // A navigation invalidates that share before any later thread sends.
          const key = frame.params?.sessionKey;
          if (sessionKey === `@route:${location.pathname}` && typeof key === "string" && key.startsWith(`agent:${agent}:`)) {
            sessionKey = key;
            notify(shared ? "shared" : "session", { revision });
          }
          else selectSession(key);
        }
        if (!shared) {
          notify("context-needed");
          queueMicrotask(() => this.dispatchEvent(new MessageEvent("message", { data: JSON.stringify({
            type: "res", id: frame.id, ok: false,
            error: { code: "INVALID_REQUEST", message: "Share the Mealie view using the panel toolbar, then send again." },
          }) })));
          return;
        }
        frame.params.__mealieContext = structuredClone(shared);
        if (frame.method === "sessions.create") creations.set(frame.id, { value: structuredClone(shared), revision, version: contextVersion });
      }
      super.send(JSON.stringify(frame));
    }
  };
  for (const method of ["pushState", "replaceState"]) {
    const original = history[method];
    history[method] = function (...args) {
      if (args[2] != null && window.__MEALIE_CONVERSATION_HOST__ && !window.__MEALIE_CONVERSATION_HOST__.allowedRoute(args[2])) return;
      const result = original.apply(this, args);
      if (location.pathname !== lastPath || path() === "/new") {
        lastPath = location.pathname;
        shared = null;
        contextVersion++;
        sessionKey = routeSession();
        notify("session");
      }
      notify("route");
      return result;
    };
  }
  window.addEventListener("popstate", () => {
    shared = null;
    contextVersion++;
    lastPath = location.pathname;
    sessionKey = routeSession();
    notify("cleared");
  });
  notify("ready");
})();
