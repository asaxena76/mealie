# Carrie in Mealie

## Production: embedded stock OpenClaw UI

The Carrie sidebar entry opens the stock UI throughout the signed-in application,
at **`https://mealie.vagabond.in/carrie/`**. The planner's legacy Ask Carrie button
is removed. Planner dates and diner filters are attached automatically; elsewhere
the panel explicitly shows the current Monday–Sunday week as its context.
Cloudflare continues to tunnel only to Mealie on Vega. Mealie authenticates and
proxies the limited UI/HTTP/WebSocket surface to a separate Vega Gateway, bound
to the private Docker bridge. No main Gateway or Tailscale hostname is exposed.

This is trusted same-origin frontend code, **not iframe security isolation**.
Review/pin OpenClaw upgrades as application-code upgrades. The backend enforces
household access, short-lived leases, an explicit RPC allowlist, connection/message
limits, and strips browser identity/forwarding headers. The Gateway independently
restricts the identity to Carrie and session read/write. Device pairing remains
manual. No administrator token is sent to the browser.

The default provisioning grants only `carrie_mealie_read`. The initial release used
the existing non-admin `vega` LMS profile by explicit owner approval. That profile is not
a database-enforced read-only credential: the fixed plugin action allowlist is
the write boundary. A dedicated Carrie identity remains the next hardening step.
Without the workflow opt-in below there are no web-search or Mealie-write tools.
Shell, scheduling and file-upload tools remain unavailable in this integration.
The model is fixed to the configured embedded-runtime model.

### Opt-in workflow tools (development first)

Provisioning remains read-only by default. `enable-workflows.mjs` explicitly enables
recipe creation/content replacement and meal-entry creation/editing/deletion via
`lms mealie`, plus public `web_search` and `web_fetch`. Shopping-list writes are
not supported by the current LMS CLI. This is not arbitrary shell or Mealie
administrator access: executable, profile, config and household remain fixed.

Install the official `@openclaw/parallel-plugin` in the target isolated Gateway
first. Copy this repository's plugin and `CARRIE-WORKFLOW-AGENTS.md` to a dedicated
directory, then run with Node 24 and the target Gateway's `OPENCLAW_STATE_DIR`:

```bash
node enable-workflows.mjs /absolute/config.json carrie-dev \
  /absolute/carrie-plugin /absolute/meal-planner-carrie/SKILL.md \
  /absolute/CARRIE-WORKFLOW-AGENTS.md /absolute/openclaw/dist/index.js --confirm
```

The script validates before replacing configuration and backs up configuration
and workspace instructions. Restart only that Gateway and start a new conversation.
The canonical skill is read in place through a fixed-file tool; no private memory
is copied or exposed. Parallel's key-free search receives search queries; keep
household/private details out of them. Web fetch is for public pages, not internal
services or a full JavaScript browser.

Draft, explicit approval, re-read, apply and read-back are conversational skill
instructions, **not an enforced approval gate**. Tools enforce allowed commands,
arguments and household binding, and never automatically retry uncertain writes.
Validate against development Mealie before separately enabling production writes.

### Focused Carrie interface

`CARRIE_STOCK_FOCUSED_UI` defaults to `true` in production. The stock chat is
hosted through OpenClaw's native conversation contract, with a Mealie-owned
conversation picker and small, version-pinned presentation overrides. Dashboard,
workspace, attachment, voice and side-panel controls are omitted. Stock model,
reasoning-effort and context-usage controls remain visible. The current Gateway
and proxy permit only `openai/gpt-5.6-sol` using the embedded OpenClaw runtime;
adding models requires updating both allowlists and retesting. The
server-side authorization boundaries above remain unchanged; hiding controls is
not a security boundary. This is a browser adaptation of a native-host contract,
not an official web UI SDK or a fork of OpenClaw.

The proxy accepts only the exact tested OpenClaw UI build fingerprint. An unknown
build returns 502 rather than falling back to the full dashboard. Retest pairing,
chat/new/switch/reopen, tool details and narrow layouts before upgrading OpenClaw.
See [the adapter notes](stock_ui/README.md#focused-conversation-adapter) for the
host contract and local test command. For an intentional presentation rollback,
set `CARRIE_STOCK_FOCUSED_UI=false` in the private Compose overlay and recreate
Mealie through the guarded deployment workflow. This restores the full stock UI
but does not expand its backend permissions. Image rollback also remains available.

### Separate Gateway on Vega

Use the installed OpenClaw 2026.10.8 / Node 24 runtime. Run
`provision-production.mjs` with absolute paths for: source config, **new** state
directory, OpenClaw entrypoint, plugin directory, generic instructions directory,
LMS config, household UUID, Docker bridge address, and reserved Mealie container
address. It copies only model/tool configuration and generic instructions, never
private memory, conversation history, skills, or model credentials. It refuses to
overwrite an existing destination. Its source config must contain `carrie-dev`.

For this deployment the named profile is `mealie`, state directory
`/home/sarathi/.openclaw-mealie`, port `18792`, bridge `172.22.0.1`, and trusted
proxy `172.22.0.2`. Verify those addresses with `docker network inspect` first.
The stock UI base path is `/carrie`. Use the **named profile** on maintenance
commands so OpenClaw does not select the main Gateway service:

```bash
openclaw --profile mealie config validate
openclaw --profile mealie devices list
openclaw --profile mealie devices approve REQUEST_ID
openclaw --profile mealie models auth login --agent carrie --provider openai --device-code
openclaw --profile mealie gateway install --port 18792 --runtime node \
  --runtime-path /absolute/path/to/node24
```

The owner completes the separate device login. Do not copy OAuth tokens from
the main/development instance. Do not enable automatic device pairing or disable
device authentication. Approve only the owner's identified browser request in
this profile; do not approve unknown requests or add administrator scopes.

### Mealie deployment and verification

Copy `deploy/vega/compose.carrie-ui.example.yaml` to the private service directory
as `compose.carrie-ui.yaml`, replace the household placeholder using the approved
LMS profile, and verify the static container address. This has no model or Gateway
credentials. Keep actual household identifiers and credential files out of Git.
The guarded deployment script includes this optional overlay. Follow
`deploy/vega/README.md`: commit, build, stage against a copied database, then deploy
with a fresh backup. **Carrie stays disabled in snapshot staging**; never point
that snapshot at the production LMS credentials.

Verify `/api/app/about`, unauthenticated `/carrie/new` returning 401, authenticated
planner launch, manual pairing, thread creation/reopening, and automatically
synchronized date/diner context. All browser traffic must stay under the Mealie origin.
Test the read tool against Mealie. For a workflow-enabled deployment, also verify
web search, a dry run and an explicitly approved fictional test entry, then clean
up that exact entry. Do not enable the old
native adapter's `CARRIE_GATEWAY_URL`/token in production.

Leases expire after 30 minutes; close/reopen Carrie to reconnect. Signing out,
closing the panel, or restarting Mealie invalidates its live leases. Conversations
remain in OpenClaw. Opening/switching threads and changing the planner range/filter
automatically synchronize the current view before sending. This is context, not
approval to modify data. Model execution
and LMS calls run on Vega, not in the browser. Use the configured public HTTPS
origin for Carrie; direct LAN HTTP access is intentionally not accepted.

To disable this integration without changing the image, remove the stock Gateway
URL from the private overlay and recreate Mealie using the deployment script's
Compose file set. Keep the Gateway state for recovery. Image/database rollback
does not delete its conversations or credentials. No Cloudflare changes are needed.

Local development continues to use a different origin and Gateway; see
[stock_ui/README.md](stock_ui/README.md).

## Earlier native panel (development / reference)

The configuration below documents the earlier custom chat adapter. It is retained
for development, **not used by the production stock-UI deployment**.

Adds a native **Ask Carrie** panel to the planner. Mealie authenticates the user and
proxies a small, fixed set of OpenClaw Gateway RPCs. OpenClaw owns the dedicated
agent, model execution, and durable sessions. The read-only plugin calls `lms mealie`
with a fixed profile and checks the authenticated household before every read.
There are no database migrations and no agent writes or schedules in this release.

Verified with OpenClaw **2026.10.8**, Gateway protocol **4**, and Node **24.22.1** on
Vega. Treat other versions as unverified; run the smoke checks below after upgrades.
Protocol documentation: <https://docs.openclaw.ai/gateway/protocol>.

## Security boundaries

- Use a separate agent and **new shared workspace**, not the private Carrie workspace.
  The supplied AGENTS/IDENTITY files contain generic shared-interface instructions.
  They do not load the canonical skill's private MEMORY.md or health records.
- Use a dedicated non-admin Mealie identity in the intended household. Keep its API
  token in an owner-only LMS credential file outside both repositories.
- The agent uses the embedded `openclaw` runtime with only `carrie_mealie_read`
  allowed. Do not switch it to a native Codex shell runtime or add shell, filesystem,
  other-agent, messaging, or scheduling tools while advertising read-only behavior.
- The plugin executes fixed argument arrays, never a shell command supplied by a
  model. It permits listing meals, diners, preparations, recipes, shopping lists,
  and reading a recipe/shopping list by ID. Unknown actions fail closed.
- The Gateway credential is privileged and **server-only**. Protocol v4 requires
  `operator.admin` for `chat.send` with `suppressCommandInterpretation: true`.
  History/abort request read/write scopes. This is not an agent-scoped Gateway token:
  the Mealie backend is a trusted boundary, and its compromise could expose Gateway
  authority. For stronger isolation, use a separate Gateway instance/credential.
- No browser token, general RPC proxy, embedded admin UI, or configurable client
  session key is exposed. WebSocket frame logging is disabled even in development.
- This adapter uses Gateway's trusted direct-loopback backend authentication.
  Reach the Gateway through a private SSH/loopback forwarding path. Do not publicly
  expose its port, disable device checks, or assume an arbitrary Docker bridge peer
  is treated as loopback. A remote paired-device client is not implemented here.
- Development, staging, and production need distinct agent IDs, LMS profiles, and
  `CARRIE_INSTANCE_ID` values. A copied staging database may retain production UUIDs;
  household matching alone cannot distinguish it. Leave Carrie disabled in staging
  until its profile is bound to the staging API.

## Set up an agent on the Gateway host

1. Install/verify the LMS CLI and a dedicated Mealie profile. Test it as the same OS
   user and with the same PATH as the Gateway. The existing Vega LMS wrapper needs
   its conda directory on PATH. `lms mealie status --profile PROFILE --config PATH
   --format json` must identify the intended household. For HTTP inside an SSH
   tunnel, LMS requires `insecure_http_origin` set to that exact loopback origin.
2. Copy this directory to a private deployment directory on the Gateway host.
   Keep it outside the agent workspace. Do not copy secrets into this repository.
3. Run the configurator with explicit absolute paths (example placeholders below).
   The script inherits the existing `lms` agent's model, forces embedded runtime,
   and installs the one-tool allowlist. It refuses an existing agent or nonempty
   workspace. It backs up the config, validates a candidate, then replaces the live
   config. OpenClaw may hot-reload plugins; coordinate this with other Gateway work.

```bash
node configure-carrie.mjs \
  /absolute/path/openclaw.json \
  /absolute/path/carrie-plugin \
  /absolute/path/CARRIE-AGENTS.md \
  carrie \
  /absolute/path/new-shared-carrie-workspace \
  /absolute/path/lms \
  /absolute/path/services.toml \
  production-profile \
  HOUSEHOLD_UUID \
  /absolute/path/conda/bin
```

`openclaw` must be on PATH under a supported Node version. Verify `openclaw config
validate`, the plugin's loaded status, and model availability for the new agent.
The configurator does not create/copy model credentials. The IDENTITY file prevents
the new agent from starting a generic onboarding interview.

## Connect Mealie

Supply these environment variables to the **backend**, not Nuxt/public runtime config:

| Variable | Value |
| --- | --- |
| `CARRIE_GATEWAY_URL` | Private forwarded WebSocket endpoint |
| `CARRIE_GATEWAY_TOKEN` | Gateway auth token, supplied through secret deployment configuration |
| `CARRIE_AGENT_ID` | Dedicated agent, e.g. `carrie` or `carrie-dev` |
| `CARRIE_HOUSEHOLD_ID` | Household UUID reported by this agent's LMS profile |
| `CARRIE_INSTANCE_ID` | Stable, unique environment name, e.g. `mealie-production` |
| `CARRIE_PROTOCOL_VERSION` | `4` (default) |

Changing instance/agent/range creates a different conversation namespace; it does
not delete existing OpenClaw history. Never bind another household to an agent
workspace that retains private context from a previous household.

For Mac development with a Gateway on Vega, a loopback-only tunnel can forward both
directions (replace SSH destination as appropriate):

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \
  -L 127.0.0.1:18790:127.0.0.1:18789 \
  -R 127.0.0.1:19900:127.0.0.1:9000 sarathi@vega
```

The development agent's LMS profile uses `http://127.0.0.1:19900`; the Mac backend
uses `ws://127.0.0.1:18790` (or `ws://host.docker.internal:18790` inside the Mac dev
container). Start `task py` with the six settings above and `task ui` as usual.
If either tunnel stops, data access/chat fails rather than falling back to production.
Do not commit tokens, local environment files, or real conversation transcripts.

For production, arrange a private forwarding path from the Mealie container to the
Gateway that arrives on Gateway loopback. Add the backend settings through private
Compose/environment configuration. Then follow **`deploy/vega/README.md`** and its
guarded build/stage/deploy process. This integration does not bypass staging or
change the production image itself.

## Verify

```bash
task py:test -- tests/integration_tests/user_household_tests/test_carrie.py
task py:check
task ui:check
task ui:build
node --test deploy/openclaw/carrie-plugin/index.test.js
```

Manual checks with fictional development data:

Run pytest commands serially: the current test harness shares and deletes
`tests/.temp` across processes. Concurrent pytest runs can invalidate each other's database.

1. Open planner → Ask Carrie. Confirm dates/diners match the planner.
2. Ask her to read the current week and diners. Confirm the answer against Mealie;
   inspect the dedicated agent's tool trace to verify only `carrie_mealie_read` ran.
3. Send a follow-up, close/reopen, and reload the page: history should survive.
4. Change dates: the new range must have a separate history. Change filters: the
   same conversation remains, with new focus included on the next send.
5. Stop a running reply. Interrupt the tunnel and confirm a bounded error, not
   secrets or a false successful save. Reconnect and review history before retrying.
6. Confirm unauthenticated users and other households cannot read/send/stop this chat.

Current limitations: plain-text messages, polling while the panel is open, recent
history only, no attachment upload, no structured approval/apply UI, no schedules,
and no private-memory access. OpenClaw remains the scheduler for the next phase;
scheduled workflows must honor explicit approval before any meal/shopping/prep writes.

To disable chat, remove the backend connection settings and restart Mealie. To undo
new Gateway provisioning, review/restore the configurator's backup (merge around
subsequent changes rather than blindly replacing them). Existing chat history stays
in OpenClaw; agent data is not deleted by these instructions.
