// Run on the Gateway host after copying carrie-plugin/ and CARRIE-AGENTS.md.
// All paths are explicit arguments; no credentials are printed or embedded.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const [configPath, pluginPath, instructionsPath, agentId, workspace, executable, servicesPath, profile, householdId, extraPath] = process.argv.slice(2);
if (!extraPath || !/^[a-z0-9_-]+$/.test(agentId)) throw new Error("Expected config, plugin, instructions, agent, workspace, LMS executable, services config, profile, household UUID, extra PATH");
const original = fs.readFileSync(configPath, "utf8");
const config = JSON.parse(original);
if (config.agents?.entries?.[agentId]) throw new Error("Agent already exists; inspect before updating");
const model = config.agents.entries.lms.model;
if (fs.existsSync(workspace) && fs.readdirSync(workspace).length) throw new Error("Use a new empty shared workspace, not Carrie's private memory workspace");
fs.mkdirSync(workspace, { recursive: true });
fs.copyFileSync(instructionsPath, path.join(workspace, "AGENTS.md"));
fs.copyFileSync(path.join(path.dirname(instructionsPath), "CARRIE-IDENTITY.md"), path.join(workspace, "IDENTITY.md"));
config.agents.entries[agentId] = {
  name: agentId === "carrie" ? "Carrie" : "Carrie Development",
  workspace,
  agentDir: path.join(path.dirname(configPath), "agents", agentId, "agent"),
  model,
  models: { [model]: { agentRuntime: { id: "openclaw" } } },
  tools: { allow: ["carrie_mealie_read"] },
  skills: [],
  memory: { search: { provider: "none" } },
};
config.plugins ??= {};
config.plugins.load ??= {};
config.plugins.load.paths = [...new Set([...(config.plugins.load.paths ?? []), pluginPath])];
if (Array.isArray(config.plugins.allow)) config.plugins.allow = [...new Set([...config.plugins.allow, "mealie-carrie"])];
config.plugins.entries ??= {};
const plugin = config.plugins.entries["mealie-carrie"] ?? { enabled: true, config: { executable, extraPath, agents: {} } };
plugin.config.agents[agentId] = { profile, configPath: servicesPath, householdId };
config.plugins.entries["mealie-carrie"] = plugin;
const backup = `${configPath}.before-${agentId}-${Date.now()}`;
fs.copyFileSync(configPath, backup);
fs.chmodSync(backup, 0o600);
const candidate = `${configPath}.candidate-${agentId}-${Date.now()}`;
fs.writeFileSync(candidate, `${JSON.stringify(config, null, 2)}\n`, { mode: 0o600, flag: "wx" });
try {
  execFileSync("openclaw", ["config", "validate"], { stdio: "pipe", env: { ...process.env, OPENCLAW_CONFIG_PATH: candidate } });
}
catch {
  throw new Error(`Configuration validation failed; live config unchanged. Inspect/remove candidate ${candidate} and the newly created workspace before retrying.`);
}
fs.renameSync(candidate, configPath);
console.log(`Configured ${agentId}; previous configuration saved at ${backup}`);
