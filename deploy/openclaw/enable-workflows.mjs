// Explicit opt-in for an existing shared Carrie agent. No credentials are copied.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const [configPath, agentId, pluginPath, skillPath, instructionsPath, openclawEntry, confirmation] = process.argv.slice(2);
if (confirmation !== "--confirm" || ![configPath, pluginPath, skillPath, instructionsPath, openclawEntry].every(value => value && path.isAbsolute(value))
  || !["carrie", "carrie-dev"].includes(agentId)) throw new Error("Expected config, Carrie agent ID, plugin directory, canonical SKILL.md, shared instructions, OpenClaw entry, --confirm");
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const agent = config.agents?.entries?.[agentId];
const binding = config.plugins?.entries?.["mealie-carrie"]?.config?.agents?.[agentId];
if (!agent || !binding || !path.isAbsolute(agent.workspace)) throw new Error("Existing shared Carrie agent/binding required");
if (path.basename(skillPath) !== "SKILL.md" || !fs.statSync(skillPath).isFile()) throw new Error("Expected canonical skill file");
if (!config.plugins?.entries?.parallel?.enabled && !config.plugins?.installs?.parallel) throw new Error("Install @openclaw/parallel-plugin in this Gateway first");
binding.writesEnabled = true;
binding.skillPath = skillPath;
agent.tools = { allow: ["carrie_mealie_read", "carrie_mealie_write", "carrie_workflow", "web_search", "web_fetch"] };
// Skill content is read through the fixed-file workflow tool, never a general read tool.
agent.skills = [];
agent.memory = { search: { provider: "none" } };
config.plugins.load ??= {};
const otherPaths = (config.plugins.load.paths ?? []).filter((directory) => {
  const manifest = path.join(directory, "openclaw.plugin.json");
  return !fs.existsSync(manifest) || JSON.parse(fs.readFileSync(manifest, "utf8")).id !== "mealie-carrie";
});
config.plugins.load.paths = [...new Set([...otherPaths, pluginPath])];
config.plugins.allow = [...new Set([...(config.plugins.allow ?? []), "mealie-carrie", "parallel", "web-readability"])];
config.plugins.entries.parallel = { ...config.plugins.entries.parallel, enabled: true };
config.plugins.entries["web-readability"] = { ...config.plugins.entries["web-readability"], enabled: true };
config.tools ??= {};
config.tools.web = {
  ...config.tools.web,
  search: { ...config.tools.web?.search, enabled: true, provider: "parallel-free" },
  fetch: { ...config.tools.web?.fetch, enabled: true },
};
const stamp = Date.now();
const candidate = `${configPath}.workflows-${stamp}.candidate`;
fs.writeFileSync(candidate, JSON.stringify(config, null, 2) + "\n", { mode: 0o600, flag: "wx" });
try {
  execFileSync(process.execPath, [openclawEntry, "config", "validate"], {
    stdio: "pipe", env: { ...process.env, OPENCLAW_CONFIG_PATH: candidate },
  });
}
catch { throw new Error("Candidate validation failed; live configuration unchanged. Inspect candidate locally."); }
const workspaceInstructions = path.join(agent.workspace, "AGENTS.md");
fs.copyFileSync(configPath, `${configPath}.before-workflows-${stamp}`);
fs.chmodSync(`${configPath}.before-workflows-${stamp}`, 0o600);
if (fs.existsSync(workspaceInstructions)) fs.copyFileSync(workspaceInstructions, `${workspaceInstructions}.before-workflows-${stamp}`);
fs.copyFileSync(instructionsPath, workspaceInstructions);
fs.renameSync(candidate, configPath);
console.log(`Enabled scoped LMS writes, canonical workflow read, and web tools for ${agentId}; rollback backups use suffix before-workflows-${stamp}. Restart this Gateway and start a new conversation.`);
