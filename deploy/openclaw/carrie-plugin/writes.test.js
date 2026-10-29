import assert from "node:assert/strict";
import { test } from "node:test";
import { buildWriteArguments, createWriteTool } from "./writes.js";
import plugin from "./index.js";

test("writes require an explicit binding opt-in", () => {
  assert.equal(createWriteTool({}, () => {}), null);
  let factory;
  plugin.register({ pluginConfig: { agents: { reader: {} } }, registerTool: value => { factory = value; } });
  assert.deepEqual(factory({ agentId: "reader" }).map(tool => tool.name), ["carrie_mealie_read"]);
});

test("fixed commands normalize values and default neither to apply nor an arbitrary CLI", () => {
  assert.deepEqual(buildWriteArguments({ action: "meal_create", mode: "dry_run", options: ["--date", "2026-11-02", "--title=--config=evil", "--everyone"] }),
    ["meal-plan", "create", "--date=2026-11-02", "--title=--config=evil", "--everyone", "--dry-run"]);
  assert.deepEqual(buildWriteArguments({ action: "meal_delete", mode: "apply", id: "42" }), ["meal-plan", "delete", "42", "--yes"]);
  for (const action of ["exec", "shopping_delete", "constructor", "__proto__"]) assert.throws(() => buildWriteArguments({ action, mode: "apply" }));
  assert.throws(() => buildWriteArguments({ action: "meal_create" }));
});

test("profile, credentials, shell and hidden mutation flags cannot escape the allowlist", () => {
  for (const options of [["--profile", "production"], ["--config=/private/secrets"], ["--yes"], ["--dry-run"], ["--format=text"], [";", "whoami"], ["--title"], ["--title", "--yes"], ["--everyone=yes"]]) {
    assert.throws(() => buildWriteArguments({ action: "meal_create", mode: "dry_run", options }));
  }
  assert.throws(() => buildWriteArguments({ action: "meal_edit", mode: "apply", id: "--help" }));
  assert.throws(() => buildWriteArguments({ action: "recipe_create", mode: "apply", options: ["--name", "a".repeat(16001)] }));
});

test("recipe content remains data, with repeated ingredients and instructions preserved", () => {
  const args = buildWriteArguments({ action: "recipe_create", mode: "dry_run", options: ["--name", "TEST bowl; $(whoami)", "--ingredient", "1 cup rice", "--ingredient", "2 cups water", "--instruction", "Cook."] });
  assert.deepEqual(args.slice(2, -1), ["--name=TEST bowl; $(whoami)", "--ingredient=1 cup rice", "--ingredient=2 cups water", "--instruction=Cook."]);
});

test("every dry-run/apply checks household before executing and never auto-retries", async () => {
  const calls = [];
  const binding = { writesEnabled: true, householdId: "fictional-household" };
  const tool = createWriteTool(binding, async args => { calls.push(args); return { household: { id: "wrong-household" } }; });
  assert.equal((await tool.execute("id", { action: "meal_delete", id: "42", mode: "apply" })).isError, true);
  assert.deepEqual(calls, [["status"]]);
  const failing = createWriteTool(binding, async args => { calls.push(args); if (args[0] === "status") return { household: { id: binding.householdId } }; throw new Error("private-token"); });
  const result = await failing.execute("id", { action: "meal_delete", id: "42", mode: "apply" });
  assert.equal(result.isError, true);
  assert.match(result.content[0].text, /uncertain/);
  assert.ok(!result.content[0].text.includes("private-token"));
  assert.equal(calls.filter(args => args[0] === "meal-plan").length, 1);
});
