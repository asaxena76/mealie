// Fixed LMS verbs/options only. Never execute model-supplied shell commands.
const recipeValues = ["name", "description", "yield", "servings", "prep-time", "cook-time", "source-url", "ingredient", "instruction"];
const mealValues = ["date", "entry-type", "recipe", "title", "text", "diner", "previous-batch", "cook-date", "cook"];
const mealFlags = ["everyone", "new-batch", "no-cooking", "clear-cook"];
const operations = {
  recipe_create: { command: ["recipe", "create"], values: recipeValues, flags: [] },
  recipe_replace: { command: ["recipe", "replace-content"], values: recipeValues, flags: [], id: true },
  meal_create: { command: ["meal-plan", "create"], values: mealValues, flags: mealFlags },
  meal_edit: { command: ["meal-plan", "edit"], values: mealValues, flags: [...mealFlags, "clear-recipe"], id: true },
  meal_delete: { command: ["meal-plan", "delete"], values: [], flags: [], id: true },
};

export function buildWriteArguments(input) {
  if (!Object.hasOwn(operations, input.action)) throw new Error("Unsupported write operation");
  if (!["dry_run", "apply"].includes(input.mode)) throw new Error("Choose dry_run or apply");
  const operation = operations[input.action];
  const args = [...operation.command];
  if (operation.id) {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}$/.test(input.id ?? "")) throw new Error("A valid record ID is required");
    args.push(input.id);
  }
  else if (input.id !== undefined) throw new Error("This operation does not accept a record ID");
  const options = input.options ?? [];
  if (!Array.isArray(options) || options.length > 200 || options.some(item => typeof item !== "string" || item.length > 16000 || item.includes("\0"))
    || JSON.stringify(options).length > 100000) throw new Error("Invalid or oversized options");
  for (let i = 0; i < options.length; i++) {
    const match = /^--([a-z-]+)(?:=(.*))?$/s.exec(options[i]);
    if (!match) throw new Error("Expected an allowed named LMS option");
    const [, name, inline] = match;
    if (operation.flags.includes(name) && inline === undefined) args.push(`--${name}`);
    else if (operation.values.includes(name)) {
      const value = inline ?? options[++i];
      if (value === undefined || (inline === undefined && value.startsWith("--"))) throw new Error(`Missing value for --${name}`);
      // The equals form prevents content beginning '-' from becoming a CLI flag.
      args.push(`--${name}=${value}`);
    }
    else throw new Error(`Unsupported option --${name}`);
  }
  args.push(input.mode === "apply" ? "--yes" : "--dry-run");
  return args;
}

export function createWriteTool(binding, run) {
  if (binding.writesEnabled !== true) return null;
  return {
    name: "carrie_mealie_write",
    label: "Write Mealie through LMS",
    description: "Scoped recipe and meal-plan writes through lms mealie. Read current state, call dry_run, show the draft, obtain explicit human approval, then call apply with the SAME options. Re-read before applying to preserve human edits, and verify afterward. Approval is conversational, not enforced by this tool. options contains CLI flags/values only (no command, profile, config, --yes or --dry-run). Recipe flags: --name --description --yield --servings --prep-time --cook-time --source-url --ingredient (repeat) --instruction (repeat). Meal flags: --date --entry-type --recipe --title --text --diner (repeat) --everyone --new-batch --previous-batch --no-cooking --cook-date --cook --clear-cook; meal_edit also --clear-recipe. Shopping writes are not supported by LMS. Never retry an uncertain write without reading back first.",
    parameters: {
      type: "object", additionalProperties: false, required: ["action", "mode"],
      properties: {
        action: { type: "string", enum: Object.keys(operations) },
        mode: { type: "string", enum: ["dry_run", "apply"] },
        id: { type: "string" },
        options: { type: "array", maxItems: 200, items: { type: "string", maxLength: 16000 } },
      },
    },
    async execute(_id, params, signal) {
      const args = buildWriteArguments(params);
      try {
        const status = await run(["status"], signal);
        if (status.household?.id !== binding.householdId) throw new Error("Household binding mismatch");
        const result = await run(args, signal);
        return { content: [{ type: "text", text: JSON.stringify(result) }] };
      }
      catch {
        return { isError: true, content: [{ type: "text", text: "LMS write failed or household binding did not match. The outcome may be uncertain. Read the exact target/range before retrying; do not claim it was saved or automatically repeat the write." }] };
      }
    },
  };
}
