<template>
  <div class="d-flex flex-wrap align-center ga-1 px-3 py-2 text-caption">
    <v-chip
      v-if="mealplan.dinerSelection.mode === 'all' && !mealplan.dinerSelection.diners.length"
      size="x-small"
      variant="tonal"
    >
      {{ $t("meal-plan.everyone") }}
    </v-chip>
    <v-chip
      v-for="diner in mealplan.dinerSelection.diners"
      :key="diner.id"
      size="x-small"
      :color="diner.color || undefined"
      variant="tonal"
      :aria-label="diner.name"
    >
      <span v-if="diner.emoji" class="me-1">{{ diner.emoji }}</span>
      {{ diner.abbreviation }}
      <v-tooltip activator="parent" location="top">
        {{ diner.name }}
      </v-tooltip>
    </v-chip>

    <span v-if="preparationText" class="d-inline-flex align-center ms-1 text-medium-emphasis">
      <v-icon size="small" class="me-1">{{ $globals.icons.chefHat }}</v-icon>
      {{ preparationText }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { format, parseISO } from "date-fns";
import type { ReadPlanEntry } from "~/lib/api/types/meal-plan";

const props = defineProps<{ mealplan: ReadPlanEntry }>();
const i18n = useI18n();

const preparationText = computed(() => {
  const preparation = props.mealplan.preparation;
  if (!preparation) return "";

  const cookName = preparation.cookDiner?.name ?? i18n.t("meal-plan.unassigned");
  if (preparation.cookDate === props.mealplan.date) {
    const laterDays = (preparation.linkedMeals ?? [])
      .filter(meal => meal.id !== props.mealplan.id && meal.date > props.mealplan.date)
      .map(meal => format(parseISO(meal.date), "EEEE"));
    const alsoEaten = laterDays.length
      ? ` · ${i18n.t("meal-plan.also-eaten", { days: laterDays.join(", ") })}`
      : "";
    return `${i18n.t("meal-plan.cook-today")} · ${cookName}${alsoEaten}`;
  }

  return i18n.t("meal-plan.from-batch", {
    day: format(parseISO(preparation.cookDate), "EEEE"),
  });
});
</script>
