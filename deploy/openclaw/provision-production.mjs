// Run on Vega with Node 24. Configuration only; never copies model credentials,
// sessions, private memory, or skills. Refuses to overwrite an existing instance.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { execFileSync } from "node:child_process";

const [sourceConfig, destination, openclawEntry, pluginPath, instructionsDirectory,
  lmsConfig, householdId, bridgeHost, proxyAddress] = process.argv.slice(2);
if (!proxyAddress || ![sourceConfig, destination, openclawEntry, pluginPath, instructionsDirectory, lmsConfig].every(path.isAbsolute)) {
  throw new Error("Provide absolute source config, new state dir, OpenClaw entry, plugin dir, instructions dir, LMS config, household UUID, bridge IP, proxy IP");
}
if (fs.existsSync(destination)) throw new Error("Refusing to overwrite existing production state");
if (!/^[a-f0-9-]{36}$/.test(householdId)) throw new Error("Expected household UUID");
if (![bridgeHost, proxyAddress].every(ip => /^172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}$/.test(ip))) {
  throw new Error("Use explicitly verified private Docker bridge addresses");
}
const source = JSON.parse(fs.readFileSync(sourceConfig, "utf8"));
const model = source.agents.entries["carrie-dev"].model;
if (typeof model !== "string") throw new Error("Expected a configured development model");
const originalPlugin = source.plugins.entries["mealie-carrie"].config;
const workspace = path.join(destination, "workspace");
const scopes = ["operator.sessions.read", "operator.sessions.write"];
const origin = "https://mealie.vagabond.in";
const config = {
  gateway: {
    mode: "local", bind: "custom", customBindHost: bridgeHost, port: 18792,
    publicOrigin: origin,
    controlUi: { basePath: "/carrie", allowedOrigins: [origin] },
    trustedProxies: [proxyAddress],
    auth: {
      mode: "trusted-proxy",
      password: crypto.randomBytes(32).toString("hex"),
      identityScopes: { mealie: scopes },
      trustedProxy: {
        userHeader: "x-mealie-user", allowUsers: ["mealie"],
        requiredHeaders: ["x-forwarded-proto", "x-forwarded-host"],
      },
    },
    roles: {
      default: "mealie",
      definitions: { mealie: {
        sessions: { others: "none" }, agents: ["carrie"], scopes,
        modelPolicy: { sourceAgent: "carrie", allow: [model] },
      } },
    },
  },
  agents: {
    defaults: { model, models: { [model]: { agentRuntime: { id: "openclaw" } } } },
    entries: { carrie: {
      name: "Carrie", workspace, agentDir: path.join(destination, "agents", "carrie", "agent"),
      model, models: { [model]: { agentRuntime: { id: "openclaw" } } },
      tools: { allow: ["carrie_mealie_read"] }, skills: [], memory: { search: { provider: "none" } },
    } },
  },
  plugins: {
    allow: ["mealie-carrie", "openai"], load: { paths: [pluginPath] },
    entries: { "mealie-carrie": { enabled: true, config: {
      executable: originalPlugin.executable, extraPath: originalPlugin.extraPath,
      agents: { carrie: { profile: "vega", configPath: lmsConfig, householdId } },
    } } },
  },
  discovery: { mdns: { mode: "off" } },
};
fs.mkdirSync(workspace, { recursive: true, mode: 0o700 });
fs.chmodSync(destination, 0o700);
for (const [from, to] of [["CARRIE-AGENTS.md", "AGENTS.md"], ["CARRIE-IDENTITY.md", "IDENTITY.md"]]) {
  fs.copyFileSync(path.join(instructionsDirectory, from), path.join(workspace, to));
}
const configPath = path.join(destination, "openclaw.json");
fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n", { mode: 0o600, flag: "wx" });
try {
  execFileSync(process.execPath, [openclawEntry, "config", "validate"], {
    stdio: "pipe",
    env: { ...process.env, OPENCLAW_STATE_DIR: destination, OPENCLAW_CONFIG_PATH: configPath },
  });
} catch {
  throw new Error("Production candidate validation failed. Main/development Gateway unchanged; inspect candidate with config validate.");
}
console.log("Created separate production Gateway configuration. Separate model login and LMS profile approval required.");
