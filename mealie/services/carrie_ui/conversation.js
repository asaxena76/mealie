// Browser adapter for OpenClaw's documented native conversation host contract.
// The Gateway/proxy remain the authorization boundary; this is presentation only.
(() => {
  const { prefix = "", agent } = document.currentScript.dataset;
  let documentId = null;
  let revision = 0;
  let list;
  let status;
  let requestThreads;
  let selectedSession = "";
  const pending = new Map();
  const root = document.documentElement;
  root.dataset.mealieChat = "loading";
  window.__OPENCLAW_NATIVE_EMBED__ = { platform: "macos", formFactor: "desktop", surface: "conversation" };
  window.__OPENCLAW_NATIVE_CONVERSATION__ = { contract: 1 };

  const validKey = key => typeof key === "string" && key.startsWith(`agent:${agent}:`);
  const allowedRoute = value => {
    try {
      const url = new URL(value, location.href);
      return url.origin === location.origin && (
        url.pathname === `${prefix}/new` && (!url.searchParams.has("agent") || url.searchParams.get("agent") === agent)
        || url.pathname.startsWith(`${prefix}/chat/${agent}/`)
      );
    }
    catch { return false; }
  };
  const command = (type, payload) => {
    if (!documentId) return;
    const requestId = crypto.randomUUID();
    pending.set(requestId, documentId);
    window.dispatchEvent(new CustomEvent("openclaw:native-conversation-command", {
      detail: { contract: 1, documentId, requestId, type, payload },
    }));
  };
  window.webkit = { messageHandlers: { openclawConversation: {
    async postMessage(message) {
      const current = window.__OPENCLAW_NATIVE_CONVERSATION_DOCUMENT__;
      if (message?.contract !== 1 || current?.contract !== 1 || typeof message.documentId !== "string"
        || !message.documentId || message.documentId !== current.documentId) return { ok: false, error: "stale-document" };
      if (message.type === "ready") {
        if (message.surface !== "conversation" || !message.capabilities?.includes("navigate")) return { ok: false, error: "unsupported" };
        documentId = message.documentId;
        revision = 0;
        pending.clear();
        root.dataset.mealieChat = "ready";
        command("presentation", { visible: true, active: true });
        return { ok: true };
      }
      if (message.documentId !== documentId) return { ok: false, error: "stale-document" };
      if (message.type === "open-dashboard") {
        if (status) status.textContent = "Only Carrie conversations are available here.";
        return { ok: false, error: "dashboard-disabled" };
      }
      if (message.type === "state") {
        if (message.context?.agentId !== agent || !validKey(message.context?.sessionKey)) return { ok: false, error: "wrong-agent" };
        if (!Number.isSafeInteger(message.revision) || message.revision <= revision) return { ok: false, error: "stale-state" };
        revision = message.revision;
        const changed = selectedSession !== message.context.sessionKey;
        selectedSession = message.context.sessionKey;
        if (list) list.value = selectedSession;
        if (changed && message.connection === "connected") requestThreads?.();
        if (status) status.textContent = message.connection === "connected" ? "" : "Connecting to Carrie…";
      }
      if (message.type === "route-changed" && (message.agentId !== agent || !validKey(message.sessionKey))) return { ok: false, error: "wrong-agent" };
      if (message.type === "command-result") {
        if (pending.get(message.requestId) !== documentId) return { ok: false, error: "unknown-request" };
        pending.delete(message.requestId);
        if (!message.ok && status) status.textContent = "Could not open this conversation. Try again.";
      }
      return { ok: true };
    },
  } } };

  // Fixed, read-only thread request via the existing authenticated transport.
  window.__MEALIE_CONVERSATION_HOST__ = {
    allowedRoute,
    connected(readThreads) { requestThreads = readThreads; requestThreads(); },
    threadsError() { if (status) status.textContent = "Could not refresh conversations. Close and reopen the panel if it has expired."; },
    threads(rows) {
      if (!list || !Array.isArray(rows)) return;
      list.replaceChildren(new Option("Choose a conversation", ""));
      for (const row of rows.filter(row => validKey(row.key) && (!row.agentId || row.agentId === agent))) {
        list.add(new Option(row.label || row.displayName || row.derivedTitle || "Untitled conversation", row.key));
      }
      list.value = selectedSession;
    },
  };
  // Native hosts own navigation. Prevent the web dashboard's global shortcuts;
  // ordinary editing, Enter-to-send and the transcript's interactions stay stock.
  window.addEventListener("keydown", event => {
    if ((event.metaKey || event.ctrlKey) && ["k", "b", ",", "/"].includes(event.key.toLowerCase())
      || (event.metaKey || event.ctrlKey) && event.shiftKey && ["s", "j", "g", "e"].includes(event.key.toLowerCase())
      || (event.metaKey || event.ctrlKey) && event.altKey
      || event.ctrlKey && event.code === "Backquote") {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
  document.addEventListener("DOMContentLoaded", () => {
    const toolbar = document.createElement("nav");
    toolbar.id = "mealie-conversations";
    toolbar.setAttribute("aria-label", "Carrie conversations");
    list = document.createElement("select");
    list.setAttribute("aria-label", "Carrie conversation");
    list.add(new Option("Choose a conversation", ""));
    list.addEventListener("change", () => { if (validKey(list.value)) command("navigate", { agentId: agent, sessionKey: list.value }); });
    const button = (label, action) => {
      const control = document.createElement("button");
      control.type = "button";
      control.textContent = label;
      control.addEventListener("click", action);
      return control;
    };
    status = document.createElement("span");
    status.setAttribute("role", "status");
    toolbar.append(list,
      button("Refresh conversations", () => requestThreads?.()),
      button("New conversation", () => location.assign(`${prefix}/new?agent=${encodeURIComponent(agent)}`)), status);
    document.body.prepend(toolbar);
    requestThreads?.();
    setTimeout(() => {
      if (!documentId) {
        root.dataset.mealieChat = "unavailable";
        status.textContent = "Carrie’s focused interface could not initialize. Close and reopen the panel.";
      }
    }, 20000);
  });
})();
