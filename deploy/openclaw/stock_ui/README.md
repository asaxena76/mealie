# Stock Carrie UI: isolated development experiment

The planner's **Carrie · OpenClaw UI** button embeds the stock Control UI served by
an isolated Gateway on Vega. It retains OpenClaw's conversations, composer, and
tool-activity display. The global **Carrie** sidebar entry replaces the legacy
planner-only **Ask Carrie** panel. Outside the planner it uses the current week;
inside the planner it automatically follows its dates and diner filters.
This page covers only the development instance. For the separate production
Gateway and same-origin `/carrie/` deployment, see [../README.md](../README.md).
There are no database migrations, meal writes, or schedules in either instance.

Verified against installed OpenClaw **2026.10.8**, protocol **4**, Node **24**.
This is a version-coupled transport adapter, not an official embedding SDK.
Retest after Gateway upgrades; do not assume another version is compatible.

## Focused-conversation adapter

Set `CARRIE_STOCK_FOCUSED_UI=1` when starting the **local** adapter to use the
Carrie-only presentation. Production enables it by default. For example:

```bash
CARRIE_STOCK_FOCUSED_UI=1 task dev:carrie-ui
```

This uses OpenClaw's documented [native conversation surface](https://docs.openclaw.ai/web/control-ui/settings),
not a fork or a rebuilt chat UI. The proxy injects a browser implementation of
the native host contract before the stock scripts. The contract was designed for
native hosts, so this browser adaptation is a tested experiment, not an official
web embedding SDK. The platform marker selects desktop presentation; it grants
no native OS access.

- A small host toolbar lists up to 100 accessible Carrie conversations, refreshes
  the list, and opens a new conversation. The existing authenticated WebSocket
  makes the fixed `sessions.list` read; no new Gateway permissions are granted.
- Native `navigate` commands switch conversations. Document IDs, request IDs and
  monotonic state revisions prevent stale acknowledgements from being adopted.
- Dashboard handoffs are rejected. A route guard limits browser-history changes
  to Carrie chat/new routes; global dashboard shortcuts are suppressed.
- A small stylesheet hides unsupported workspace, attachment, voice and
  side-panel controls. Stock model/effort settings and context usage stay visible.
  Model mutations are limited to `openai/gpt-5.6-sol` and the embedded runtime;
  keep the proxy allowlist aligned with the dedicated Gateway when adding models.
  Transcript rendering, inline tool activity, drafts, sending
  and stopping remain stock. These presentation rules are **not authorization**.
- The proxy requires the exact tested stock build fingerprint, otherwise it
  returns 502 instead of embedding an untested dashboard. The stock application
  stays hidden until the native bridge acknowledges readiness; a missing handshake
  shows an unavailable message. Never remove this check merely to upgrade.

The files are `mealie/services/carrie_ui/conversation.js` and `conversation.css`;
the transport stays in `bridge.js`. Turning off the flag restores the normal
stock presentation without changing conversations, pairing, credentials or data.
Before releases and OpenClaw upgrades, retest fresh-browser pairing, desktop/mobile layout,
thread switching/new/reopen, streaming/stop, tool details, keyboard navigation,
context synchronization before sending, and the unknown-build failure state.
Current context is attached automatically per conversation; no Mealie writes are enabled.

## How to use

1. Open Mealie at `http://localhost:3000`, sign into the development household,
   and open the meal planner. Choose the dates and diner/cooking filters.
2. Open **Carrie · OpenClaw UI**. A new browser may require one-time device pairing
   on the isolated Gateway (instructions below). There is no automatic pairing.
3. Choose a conversation or **New conversation**, then send a plain-text request.
   The current dates and diner/cooking filters are attached automatically.
   In focused mode the composer stays inactive until context connects, with an inline
   instruction. This prevents stock new-session optimistic navigation from getting
   stuck after a rejected unshared send; drafts are preserved. The transport and
   server still reject unshared sends independently of this presentation guard.
4. Carrie receives the dates, selected diner UUIDs, and cooking-filter flag with
   each message, and can read the development data through the fixed LMS profile.
   An empty diner selection means everyone. Context is an intent hint, not a
   database snapshot or authorization boundary; Carrie still reads current data.

Changing filters, switching conversations, opening a new conversation, or closing
and reopening the panel replaces the context automatically. The panel remembers
the last thread while the planner component is mounted; a full page reload starts
at New conversation. Old context remains in conversation history, so the latest
current view context accompanies every subsequent message. Context synchronization
does not approve any recipe, meal-plan, shopping, or preparation changes.

This isolated instance has **new conversations and separate model credentials**.
It does not import the main Gateway's conversations or Carrie's private memory.
The context annotation is visible in the stock transcript in this prototype.

## Runtime layout

| Component | Listen/connect address |
| --- | --- |
| Local Mealie UI / API | localhost:3000 / 127.0.0.1:9000 |
| Local UI adapter (`proxy.py`) | 127.0.0.1:18800 |
| Local SSH forward to isolated Gateway | 127.0.0.1:18793 → Vega 127.0.0.1:18791 |
| Vega LMS development API forward | Vega 127.0.0.1:19900 → local 127.0.0.1:9000 |

The adapter serves stock assets unchanged and injects `bridge.js` into the HTML
shell, plus the conversation host script/styles when focused presentation is enabled.
The bridge wraps fetch/WebSocket transport and shares context through a
small origin-checked `postMessage` contract. It does not scrape the UI or rebuild
the transcript. The adapter narrowly adjusts the stock frame-ancestors policy to
allow the exact Mealie development origin; other CSP directives remain intact.

## Provision a new isolated Gateway on Vega

Prerequisites: the existing read-only plugin and `carrie-dev` LMS binding from
the parent README, a working development API tunnel, and the installed version
above. Copy this directory and the generic CARRIE instruction files to a private
deployment directory outside any agent workspace. Do not copy private memory.

Run `provision.mjs` with **absolute paths**, replacing these placeholders:

```bash
node provision.mjs \
  /absolute/path/existing/openclaw.json \
  /absolute/path/NEW-isolated-state-directory \
  /absolute/path/openclaw/dist/index.js \
  /absolute/path/carrie-plugin \
  /absolute/path/directory-containing-CARRIE-AGENTS-and-IDENTITY
```

The provisioner refuses an existing destination. It reads only the source's
development model and plugin binding into the new configuration; it does not
modify the source or copy sessions, credentials, or private workspace content.
The two supplied instruction files must be the generic files in this repository.
It creates a random local CLI maintenance password that stays server-side.

For the existing experiment the state directory is
`/home/sarathi/.openclaw-mealie-ui-dev`, and the transient user unit is
`mealie-stock-ui-dev.service`. **Do not provision that directory again.**
For a new installation, export these variables in a dedicated shell using its
new directory (never the main instance's directory):

```bash
export OPENCLAW_STATE_DIR=/absolute/path/NEW-isolated-state-directory
export OPENCLAW_CONFIG_PATH="$OPENCLAW_STATE_DIR/openclaw.json"
openclaw config validate
openclaw models auth login --provider openai --method device-code
```

Complete the login yourself in the provider's browser. Keep the configured model
and tool restrictions. Then start the isolated Gateway in the foreground:

```bash
openclaw gateway --port 18791 --bind loopback
```

Alternatively use a separately named user service with those same state/config
environment variables. The current transient service can be restarted with
`systemctl --user restart mealie-stock-ui-dev.service`; it is not a permanent
boot-time installation. Never restart the main Gateway to restart this experiment.

### Device pairing

With the isolated state/config variables set in that dedicated Vega shell:

```bash
openclaw devices list
openclaw devices approve REQUEST_ID
```

Inspect the pending request and approve only the browser you just opened, with
only `operator.sessions.read` and `operator.sessions.write` requested. If it asks
for broader scopes, stop and check the isolated identity/role configuration; do
not approve it. The test browser was paired manually. Check `devices approve
--help` on upgrades. Do not grant admin scopes or disable device authentication.

## Start the Mac development side

Keep the existing `task py` and `task ui` development services running. The
household UUID must match the development LMS profile, not production. Keep this
value in local environment configuration, never in a committed fixture.

Start the loopback-only forward in a dedicated terminal:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18793:127.0.0.1:18791 sarathi@vega
```

LMS also needs the reverse forward below. Do not start it twice if the existing
Carrie development tunnel already owns port 19900:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -R 127.0.0.1:19900:127.0.0.1:9000 sarathi@vega
```

From the repository on the **Mac host**, with `uv` and `task` installed:

```bash
export CARRIE_HOUSEHOLD_ID=DEVELOPMENT_HOUSEHOLD_UUID
task dev:carrie-ui
```

This runs an isolated Python environment with pinned adapter dependencies. It
does not install into or replace the Linux dev container's shared `.venv`.
The equivalent command without Task is:

```bash
CARRIE_STOCK_DEV=1 uv run --isolated --no-project \
  --with-requirements deploy/openclaw/stock_ui/requirements.txt \
  uvicorn deploy.openclaw.stock_ui.proxy:app_factory --factory \
  --host 127.0.0.1 --port 18800 --ws-max-size 131072 --no-access-log --log-level warning
```

Use exactly `localhost:3000` for the parent UI and `127.0.0.1:18800` for the
embedded UI. The distinct hosts isolate their browser storage. Do not publish
the adapter or tunnels through a reverse proxy, Tailscale Serve, or a LAN listener.
To stop, Ctrl-C the local adapter/tunnel terminals and stop only the isolated
Vega service with `systemctl --user stop mealie-stock-ui-dev.service`.
This preserves its separate state and conversations.

## Security and deliberate limitations

- Mealie verifies the logged-in user belongs to the configured development
  household. A separate per-panel lease lasts 30 minutes, is held in memory, and
  is revoked on close/logout. Reopen the panel after expiry or adapter restart.
  Mealie authentication is rechecked when opening WebSocket connections and
  sending messages. No bearer token goes in an iframe URL, log, or stock UI.
- Trusted identity headers are created server-side, never accepted from the
  browser. The Gateway role allows only `carrie-dev`, its chosen model, owned
  conversations, and `operator.sessions.read` / `operator.sessions.write`.
  All development-household users share the `mealie-dev` conversation identity.
  This is not a per-person multi-tenant deployment design.
- Loopback trusted-proxy mode **trusts local OS processes** on the Mac and Vega.
  They can reach the forwarded Gateway and assert the fixed development identity.
  The adapter uses a synthetic documentation-range forwarded IP, not an audited
  client IP. This is suitable only for this isolated, single-owner dev setup.
- Carrie has only `carrie_mealie_read`, with the LMS profile fixed server-side.
  It cannot write meals, execute a general shell, read private memory, invoke
  other agents, or create schedules. Human-approved write workflows are later work.
- With focused presentation disabled, the stock UI displays out-of-scope controls. Admin configuration,
  schedules, arbitrary tool execution, attachments, workspace changes, external
  delivery, runtime switching, and slash commands are not supported here.
  Thread organization is supported; deletion is not. Restricted cosmetic/config
  requests and disabled service-worker registration can produce console warnings.
  Reopening a conversation uses the scoped `chat.startup` transcript read; this
  requires no planner context. Sending a message requires valid current-view
  context, synchronized automatically by the Mealie panel.
  Do not fix these by granting broader Gateway scopes.
- The bridge validates message origin, source window, document, and thread.
  Context is per iframe, not global browser storage. Diner UUIDs are format-checked
  hints; the fixed LMS household binding, not those hints, enforces data access.
- This does not claim a fully supported or production-hardened embedding API.
  A production design needs deployment authentication, HTTPS, pairing lifecycle,
  multi-household isolation, resource limits, and explicit supported UI actions.

## Verification

```bash
task dev:carrie-ui:test
```

Read-only live authorization probe (requires the isolated port-18793 tunnel):

```bash
uv run --isolated --no-project \
  --with-requirements deploy/openclaw/stock_ui/requirements.txt \
  python -m deploy.openclaw.stock_ui.probe
```

Expected: only session read/write scopes, `agents.list` and `sessions.list`
allowed, `config.get` and `tools.invoke` denied. It prints no credentials/history.

Browser smoke test: choose dates/filters, ask Carrie to read meals and diners
without changing data, verify the answer and tool activity; switch/new/reopen
conversations and confirm context updates automatically. Repeat in two tabs with different
filters. The bridge's automated tests cover cross-tab/document/session isolation
and late replies after context is cleared. Run `task ui:check` for Mealie changes.
