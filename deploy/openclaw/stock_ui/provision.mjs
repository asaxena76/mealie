// Run on Vega. Creates a NEW state directory; never edits the existing Gateway.
// No credentials, sessions, or memory are copied. Model login is a separate step.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const [sourceConfig, destination, openclawEntry, pluginPath, instructionsDirectory] = process.argv.slice(2);
if (!instructionsDirectory || ![sourceConfig, destination, openclawEntry, pluginPath, instructionsDirectory].every(path.isAbsolute)) {
  throw new Error("Expected absolute source config, NEW state directory, OpenClaw entry, plugin path, instructions directory");
}
if (fs.existsSync(destination)) throw new Error("Refusing to overwrite an existing state directory");
const source = JSON.parse(fs.readFileSync(sourceConfig, "utf8"));
const model = source.agents.entries["carrie-dev"].model;
if (typeof model !== "string") throw new Error("Expected the development agent's single model");
const originalPlugin = source.plugins.entries["mealie-carrie"].config;
const workspace = path.join(destination, "workspace");
fs.mkdirSync(workspace, { recursive: true, mode: 0o700 });
fs.chmodSync(destination, 0o700);
for (const [from, to] of [["CARRIE-AGENTS.md", "AGENTS.md"], ["CARRIE-IDENTITY.md", "IDENTITY.md"]]) {
  fs.copyFileSync(path.join(instructionsDirectory, from), path.join(workspace, to));
}
const config = {
  gateway: {
    mode: "local", bind: "loopback", port: 18791,
    publicOrigin: "http://127.0.0.1:18800",
    trustedProxies: ["127.0.0.1", "::1"],
    controlUi: { allowedOrigins: ["http://127.0.0.1:18800"] },
    auth: {
      mode: "trusted-proxy",
      // Local CLI maintenance only; never exposed by the proxy or browser.
      password: crypto.randomBytes(32).toString("hex"),
      identityScopes: { "mealie-dev": ["operator.sessions.read", "operator.sessions.write"] },
      trustedProxy: {
        userHeader: "x-mealie-user", allowUsers: ["mealie-dev"], allowLoopback: true,
        requiredHeaders: ["x-forwarded-proto", "x-forwarded-host"],
      },
    },
    roles: {
      default: "mealie",
      definitions: {
        mealie: {
          sessions: { others: "none" }, agents: ["carrie-dev"],
          scopes: ["operator.sessions.read", "operator.sessions.write"],
          modelPolicy: { sourceAgent: "carrie-dev", allow: [model] },
        },
      },
    },
  },
  agents: {
    defaults: { model, models: { [model]: { agentRuntime: { id: "openclaw" } } } },
    entries: {
      "carrie-dev": {
        name: "Carrie UI Development", workspace,
        agentDir: path.join(destination, "agents", "carrie-dev", "agent"),
        model, models: { [model]: { agentRuntime: { id: "openclaw" } } },
        tools: { allow: ["carrie_mealie_read"] }, skills: [],
        memory: { search: { provider: "none" } },
      },
    },
  },
  plugins: {
    allow: ["mealie-carrie", "openai"],
    load: { paths: [pluginPath] },
    entries: {
      "mealie-carrie": {
        enabled: true,
        config: {
          executable: originalPlugin.executable, extraPath: originalPlugin.extraPath,
          agents: { "carrie-dev": originalPlugin.agents["carrie-dev"] },
        },
      },
    },
  },
  discovery: { mdns: { mode: "off" } },
};
const configPath = path.join(destination, "openclaw.json");
fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n", { mode: 0o600, flag: "wx" });
try {
  execFileSync(process.execPath, [openclawEntry, "config", "validate"], {
    stdio: "pipe",
    env: { ...process.env, OPENCLAW_STATE_DIR: destination, OPENCLAW_CONFIG_PATH: configPath },
  });
} catch {
  throw new Error("Isolated config validation failed. Main Gateway unchanged; inspect the new config with OpenClaw config validate.");
}
console.log("Created isolated development config. No credentials or conversation history copied. Model login required.");
