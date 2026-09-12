import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

type FilterableMealPlan = Pick<ReadPlanEntry, "dinerSelection" | "preparation">;

export function mealPlanMatchesDinerFilter(
  mealplan: FilterableMealPlan,
  selectedDinerIds: ReadonlySet<string>,
  includeCooking = true,
) {
  if (!selectedDinerIds.size || mealplan.dinerSelection.mode === "all") {
    return true;
  }

  const isEating = mealplan.dinerSelection.dinerIds.some(id => selectedDinerIds.has(id))
    || mealplan.dinerSelection.diners.some(diner => selectedDinerIds.has(diner.id));
  const cookDinerId = mealplan.preparation?.cookDinerId ?? mealplan.preparation?.cookDiner?.id;

  return isEating || (includeCooking && Boolean(cookDinerId && selectedDinerIds.has(cookDinerId)));
}
