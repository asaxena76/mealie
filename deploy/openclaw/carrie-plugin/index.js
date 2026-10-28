import { execFile } from "node:child_process";
import { promisify } from "node:util";

const executeFile = promisify(execFile);
const actions = {
  meals: ["meal-plan", "list"],
  diners: ["diner", "list"],
  preparations: ["meal-preparation", "list"],
  recipes: ["recipe", "list"],
  recipe: ["recipe", "show"],
  shopping_lists: ["shopping-list", "list"],
  shopping_list: ["shopping-list", "show"],
};

export function buildArguments(input) {
  if (!Object.hasOwn(actions, input.action)) throw new Error("Unsupported read operation");
  const args = [...actions[input.action]];
  if (["meals", "preparations"].includes(input.action)) {
    if (![input.start, input.end].every(value => /^\d{4}-\d{2}-\d{2}$/.test(value ?? ""))) {
      throw new Error("A date range is required");
    }
    if (!Number.isFinite(Date.parse(input.start)) || !Number.isFinite(Date.parse(input.end))
      || Date.parse(input.end) < Date.parse(input.start)
      || Date.parse(input.end) - Date.parse(input.start) > 62 * 86400000) {
      throw new Error("Invalid date range");
    }
    args.push("--start", input.start, "--end", input.end);
  }
  if (["recipe", "shopping_list"].includes(input.action)) {
    if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,199}$/.test(input.id ?? "")) throw new Error("A valid record ID is required");
    args.push(input.id);
  }
  else {
    const page = input.page ?? 1;
    if (!Number.isInteger(page) || page < 1 || page > 100) throw new Error("Invalid page");
    args.push("--page", String(page), "--limit", "50");
  }
  if (input.action === "recipes" && input.search) {
    if (typeof input.search !== "string" || input.search.length > 200) throw new Error("Invalid recipe search");
    args.push(`--search=${input.search}`);
  }
  return args;
}

export default {
  id: "mealie-carrie",
  name: "Mealie Carrie",
  register(api) {
    const config = api.pluginConfig;
    api.registerTool((context) => {
      const binding = config.agents?.[context.agentId];
      if (!binding) return null;
      async function run(args, signal) {
        const { stdout } = await executeFile(config.executable, [
          "mealie", ...args, "--profile", binding.profile, "--config", binding.configPath, "--format", "json",
        ], {
          timeout: 30000,
          maxBuffer: 1000000,
          signal,
          env: { ...process.env, PATH: `${config.extraPath ?? ""}:${process.env.PATH ?? ""}` },
        });
        return JSON.parse(stdout);
      }
      return {
        name: "carrie_mealie_read",
        label: "Read Mealie through LMS",
        description: "Read the current household meal plan, diners, cooking batches, recipes or shopping lists using lms mealie. Read meals and diners first; read recipes by ID for ingredients. Use the displayed date range. Results are paginated: fetch further pages when total_pages indicates more. This tool cannot change data.",
        parameters: {
          type: "object", additionalProperties: false, required: ["action"],
          properties: {
            action: { type: "string", enum: Object.keys(actions) },
            start: { type: "string" }, end: { type: "string" },
            id: { type: "string" }, search: { type: "string" },
            page: { type: "integer", minimum: 1, maximum: 100 },
          },
        },
        async execute(_id, params, signal) {
          const args = buildArguments(params);
          try {
            const status = await run(["status"], signal);
            if (status.household?.id !== binding.householdId) throw new Error("Household binding mismatch");
            const result = await run(args, signal);
            return { content: [{ type: "text", text: JSON.stringify(result) }] };
          }
          catch {
            return { isError: true, content: [{ type: "text", text: "LMS read failed or household binding did not match. Do not guess stored data. Ask the administrator to check the Carrie LMS profile." }] };
          }
        },
      };
    }, { names: ["carrie_mealie_read"], optional: true });
  },
};
