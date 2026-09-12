import { describe, expect, test } from "vitest";
import type { DinerSelectionOut, ReadMealPreparation } from "~/lib/api/types/meal-plan";
import { mealPlanMatchesDinerFilter } from "./diner-filter";

function mealplan(
  mode: DinerSelectionOut["mode"],
  dinerIds: string[] = [],
  cookDinerId?: string,
) {
  return {
    dinerSelection: {
      mode,
      dinerIds,
      diners: dinerIds.map(id => ({
        id,
        name: id,
        abbreviation: id.slice(0, 2),
      })),
    },
    preparation: cookDinerId
      ? { cookDinerId } as ReadMealPreparation
      : null,
  };
}

describe("mealPlanMatchesDinerFilter", () => {
  test("shows every meal when no diner is selected", () => {
    expect(mealPlanMatchesDinerFilter(mealplan("selected", ["alex"]), new Set())).toBe(true);
  });

  test("always shows meals tagged for everyone", () => {
    expect(mealPlanMatchesDinerFilter(mealplan("all"), new Set(["blair"]))).toBe(true);
  });

  test("shows a meal when a selected diner is eating it", () => {
    expect(mealPlanMatchesDinerFilter(mealplan("selected", ["alex"]), new Set(["alex"]))).toBe(true);
  });

  test("shows a meal when a selected diner is cooking it", () => {
    expect(mealPlanMatchesDinerFilter(mealplan("selected", ["blair"], "alex"), new Set(["alex"]))).toBe(true);
  });

  test("matches any selected diner", () => {
    expect(mealPlanMatchesDinerFilter(mealplan("selected", ["casey"], "drew"), new Set(["alex", "drew"]))).toBe(true);
  });

  test("hides meals unrelated to every selected diner", () => {
    expect(mealPlanMatchesDinerFilter(mealplan("selected", ["blair"], "casey"), new Set(["alex"]))).toBe(false);
  });
});
