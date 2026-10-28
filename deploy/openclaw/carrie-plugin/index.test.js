import assert from "node:assert/strict";
import { test } from "node:test";
import plugin, { buildArguments } from "./index.js";

test("only enumerated read commands can reach LMS", () => {
  for (const action of ["delete", "create", "__proto__", "constructor", "meals; whoami"]) {
    assert.throws(() => buildArguments({ action }));
  }
  assert.throws(() => buildArguments({ action: "recipe", id: "--help" }));
  assert.throws(() => buildArguments({ action: "meals", start: "2026-01-01", end: "2027-01-01" }));
  assert.throws(() => buildArguments({ action: "diners", page: -1 }));
  assert.deepEqual(buildArguments({ action: "recipes", search: "--yes; $(touch x)" }), [
    "recipe", "list", "--page", "1", "--limit", "50", "--search=--yes; $(touch x)",
  ]);
});

test("tool is unavailable to agents without an explicit binding", () => {
  let factory;
  plugin.register({ pluginConfig: { agents: {} }, registerTool: fn => { factory = fn; } });
  assert.equal(factory({ agentId: "other" }), null);
});
