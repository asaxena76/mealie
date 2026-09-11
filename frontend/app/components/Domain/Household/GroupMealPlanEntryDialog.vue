<template>
  <BaseDialog
    v-model="dialog"
    :title="entry ? $t('meal-plan.update-this-meal-plan') : $t('meal-plan.create-a-new-meal-plan')"
    :submit-text="entry ? $t('general.update') : $t('general.create')"
    :icon="$globals.icons.foods"
    :submit-disabled="submitDisabled"
    color="primary"
    width="1000"
    can-submit
    disable-submit-on-enter
    @submit="submit"
  >
    <v-card-text>
      <v-row>
        <v-col
          cols="12"
          md="5"
        >
          <v-btn-toggle
            v-model="entryMode"
            mandatory
            divided
            variant="outlined"
            color="primary"
            class="w-100 mb-4"
          >
            <v-btn
              value="recipe"
              class="flex-grow-1"
            >
              <v-icon start>
                {{ $globals.icons.silverwareForkKnife }}
              </v-icon>
              {{ $t("general.recipe") }}
            </v-btn>
            <v-btn
              value="note"
              class="flex-grow-1"
            >
              <v-icon start>
                {{ $globals.icons.textBox }}
              </v-icon>
              {{ $t("meal-plan.note") }}
            </v-btn>
          </v-btn-toggle>

          <v-date-picker
            v-model="selectedDate"
            class="mx-auto"
            hide-header
            show-adjacent-months
            color="primary"
            :first-day-of-week="firstDayOfWeek"
          />

          <v-select
            v-model="entryType"
            class="mt-4"
            :items="planTypeOptions"
            :label="$t('recipe.entry-type')"
            item-title="text"
            item-value="value"
            :return-object="false"
            hide-details
          />
        </v-col>

        <!-- both modes fill the same pane, so the dialog doesn't resize when switching between them -->
        <v-col
          cols="12"
          md="7"
          class="entry-detail"
        >
          <RecipeSelector
            v-if="isRecipe"
            ref="selector"
            v-model="recipe"
            height="auto"
            :query-filter="ruleQueryFilter"
          >
            <template #filters>
              <v-switch
                v-model="ignoreRules"
                class="ignore-rules-switch flex-grow-0 ms-auto"
                color="primary"
                density="compact"
                hide-details
                :disabled="!applicableRuleFilter"
                :label="$t('meal-plan.ignore-rules')"
              />
            </template>

            <template #no-results>
              <v-alert
                v-if="ruleQueryFilter"
                type="info"
                variant="tonal"
              >
                <div>{{ $t("meal-plan.no-recipes-match-your-rules") }}</div>
                <v-btn
                  class="mt-2"
                  size="small"
                  color="info"
                  variant="tonal"
                  @click="ignoreRules = true"
                >
                  {{ $t("meal-plan.ignore-rules") }}
                </v-btn>
              </v-alert>
              <v-alert
                v-else
                type="info"
                variant="tonal"
                :text="$t('search.no-results')"
              />
            </template>
          </RecipeSelector>

          <div v-else>
            <v-text-field
              v-model="title"
              :label="$t('meal-plan.meal-title')"
              :rules="[validators.required]"
            />
            <v-textarea
              v-model="text"
              :label="$t('meal-plan.meal-note')"
              rows="6"
            />
          </div>
        </v-col>
      </v-row>

      <v-divider class="my-4" />

      <section>
        <div class="text-subtitle-1 mb-2">
          {{ $t("meal-plan.who-is-eating") }}
        </div>
        <div class="d-flex flex-wrap ga-2">
          <v-chip
            :color="dinerMode === 'all' ? 'primary' : undefined"
            :variant="dinerMode === 'all' ? 'flat' : 'outlined'"
            @click="selectEveryone"
          >
            {{ $t("meal-plan.everyone") }}
          </v-chip>
          <v-chip
            v-for="diner in activeDiners"
            :key="diner.id"
            :color="selectedDinerIds.includes(diner.id) ? (diner.color || 'primary') : undefined"
            :variant="selectedDinerIds.includes(diner.id) ? 'flat' : 'outlined'"
            :aria-label="diner.name"
            @click="toggleDiner(diner.id)"
          >
            <span v-if="diner.emoji" class="me-1">{{ diner.emoji }}</span>
            {{ diner.abbreviation }}
            <v-tooltip activator="parent" location="top">
              {{ diner.name }}
            </v-tooltip>
          </v-chip>
        </div>
      </section>

      <section v-if="isRecipe" class="mt-5">
        <div class="text-subtitle-1 mb-2">
          {{ $t("meal-plan.cooking-intention") }}
        </div>
        <v-radio-group v-model="preparationMode" inline hide-details>
          <v-radio value="create" :label="$t('meal-plan.cook-for-this-meal')" />
          <v-radio value="existing" :label="$t('meal-plan.from-existing-batch')" />
          <v-radio value="none" :label="$t('meal-plan.no-cooking-intention')" />
        </v-radio-group>

        <v-row v-if="preparationMode === 'create'" class="mt-1">
          <v-col cols="12" sm="6">
            <v-text-field v-model="cookDate" type="date" :label="$t('meal-plan.cook-on')" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-select
              v-model="cookDinerId"
              :items="cookOptions"
              :label="$t('meal-plan.who-is-cooking')"
              item-title="title"
              item-value="value"
              clearable
            />
          </v-col>
        </v-row>

        <v-select
          v-else-if="preparationMode === 'existing'"
          v-model="preparationId"
          class="mt-3"
          :items="preparationOptions"
          :label="$t('meal-plan.from-existing-batch')"
          item-title="title"
          item-value="value"
          :no-data-text="$t('meal-plan.no-existing-batches')"
        />
      </section>
    </v-card-text>
  </BaseDialog>
</template>

<script setup lang="ts">
import { format } from "date-fns";
import RecipeSelector from "~/components/Domain/Recipe/RecipeSelector.vue";
import { usePlanTypeOptions } from "~/composables/use-group-mealplan";
import { buildRuleQueryFilter, useMealplanRules } from "~/composables/use-mealplan-rules";
import { useHouseholdSelf } from "~/composables/use-households";
import { useHouseholdDiners } from "~/composables/use-household-diners";
import { validators } from "~/composables/use-validators";
import { useUserApi } from "~/composables/api";
import type {
  CreatePlanEntry,
  DinerSelectionMode,
  PlanEntryType,
  ReadMealPreparation,
  ReadPlanEntry,
  UpdatePlanEntry,
} from "~/lib/api/types/meal-plan";
import type { RecipeSummary } from "~/lib/api/types/recipe";

interface Props {
  entry?: ReadPlanEntry | null;
  date?: Date | null;
}
const props = withDefaults(defineProps<Props>(), {
  entry: null,
  date: null,
});

const emit = defineEmits<{
  create: [payload: CreatePlanEntry];
  update: [payload: UpdatePlanEntry];
}>();

const dialog = defineModel<boolean>({ required: true });

const { household } = useHouseholdSelf();
const { activeDiners } = useHouseholdDiners();
const api = useUserApi();
const { rules } = useMealplanRules();
const planTypeOptions = usePlanTypeOptions();

const selector = ref<InstanceType<typeof RecipeSelector> | null>(null);

const entryMode = ref<"recipe" | "note">("recipe");
const selectedDate = ref(new Date());
const entryType = ref<PlanEntryType>("dinner");
const recipe = ref<RecipeSummary | null>(null);
const title = ref("");
const text = ref("");
const ignoreRules = ref(false);
const dinerMode = ref<DinerSelectionMode>("all");
const selectedDinerIds = ref<string[]>([]);
const preparationMode = ref<"create" | "existing" | "none">("create");
const preparationId = ref<string | null>(null);
const cookDate = ref("");
const cookDinerId = ref<string | null>(null);
const preparations = ref<ReadMealPreparation[]>([]);

const isRecipe = computed(() => entryMode.value === "recipe");
const firstDayOfWeek = computed(() => household.value?.preferences?.firstDayOfWeek || 0);

const applicableRuleFilter = computed(() => buildRuleQueryFilter(rules.value, selectedDate.value, entryType.value));
const ruleQueryFilter = computed(() => ignoreRules.value ? null : applicableRuleFilter.value);

const submitDisabled = computed(() => {
  if (!isRecipe.value) return !title.value.trim();
  if (!recipe.value) return true;
  if (preparationMode.value === "existing") return !preparationId.value;
  if (preparationMode.value === "create") {
    return !cookDate.value || cookDate.value > format(selectedDate.value, "yyyy-MM-dd");
  }
  return false;
});
const cookOptions = computed(() => [
  { title: i18n.t("meal-plan.unassigned"), value: null },
  ...activeDiners.value.map(diner => ({
    title: `${diner.emoji ? `${diner.emoji} ` : ""}${diner.name}`,
    value: diner.id,
  })),
]);
const preparationOptions = computed(() => preparations.value
  .filter(item => item.recipeId === recipe.value?.id && item.cookDate <= format(selectedDate.value, "yyyy-MM-dd"))
  .map(item => ({
    title: `${item.cookDate} · ${item.cookDiner?.name ?? i18n.t("meal-plan.unassigned")}`,
    value: item.id,
  })));

const i18n = useI18n();

function parseEntryDate(date: string) {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(year, month - 1, day);
}

async function initialize() {
  entryMode.value = props.entry && !props.entry.recipeId ? "note" : "recipe";
  selectedDate.value = props.entry ? parseEntryDate(props.entry.date) : props.date ?? new Date();
  entryType.value = props.entry?.entryType ?? "dinner";
  recipe.value = props.entry?.recipe ?? null;
  title.value = props.entry?.title ?? "";
  text.value = props.entry?.text ?? "";
  ignoreRules.value = false;
  dinerMode.value = props.entry?.dinerSelection.mode ?? "all";
  selectedDinerIds.value = props.entry?.dinerSelection.mode === "selected"
    ? props.entry.dinerSelection.diners.map(diner => diner.id)
    : [];
  const existingPreparation = props.entry?.preparation;
  if (existingPreparation) {
    preparationMode.value = existingPreparation.cookDate === props.entry?.date ? "create" : "existing";
    preparationId.value = existingPreparation.id;
    cookDate.value = existingPreparation.cookDate;
    cookDinerId.value = existingPreparation.cookDinerId ?? null;
  }
  else {
    preparationMode.value = isRecipe.value ? "create" : "none";
    preparationId.value = null;
    cookDate.value = format(selectedDate.value, "yyyy-MM-dd");
    cookDinerId.value = null;
  }
  const { data } = await api.mealPreparations.getAll(1, -1);
  preparations.value = data?.items ?? [];
  selector.value?.reset();
}

function selectEveryone() {
  dinerMode.value = "all";
  selectedDinerIds.value = [];
}

function toggleDiner(id: string) {
  if (dinerMode.value === "all") {
    dinerMode.value = "selected";
    selectedDinerIds.value = [id];
    return;
  }

  selectedDinerIds.value = selectedDinerIds.value.includes(id)
    ? selectedDinerIds.value.filter(dinerId => dinerId !== id)
    : [...selectedDinerIds.value, id];

  if (!selectedDinerIds.value.length || selectedDinerIds.value.length === activeDiners.value.length) {
    selectEveryone();
  }
}

function submit() {
  const payload = {
    date: format(selectedDate.value, "yyyy-MM-dd"),
    entryType: entryType.value,
    title: isRecipe.value ? "" : title.value,
    text: isRecipe.value ? "" : text.value,
    recipeId: isRecipe.value ? recipe.value?.id : null,
    dinerSelection: {
      mode: dinerMode.value,
      dinerIds: dinerMode.value === "selected" ? selectedDinerIds.value : [],
    },
    preparationIntent: buildPreparationIntent(),
  };

  if (props.entry) {
    emit("update", {
      ...payload,
      id: props.entry.id,
      groupId: props.entry.groupId,
      userId: props.entry.userId,
    });
  }
  else {
    emit("create", payload);
  }
}

function buildPreparationIntent() {
  if (!isRecipe.value || preparationMode.value === "none") {
    return { mode: "none" as const };
  }
  if (preparationMode.value === "existing") {
    return { mode: "existing" as const, preparationId: preparationId.value };
  }
  if (props.entry?.preparation) {
    return {
      mode: "existing" as const,
      preparationId: props.entry.preparation.id,
      cookDate: cookDate.value,
      cookDinerId: cookDinerId.value,
    };
  }
  return {
    mode: "create" as const,
    cookDate: cookDate.value,
    cookDinerId: cookDinerId.value,
  };
}

watch(selectedDate, (date) => {
  if (!props.entry?.preparation && preparationMode.value === "create") {
    cookDate.value = format(date, "yyyy-MM-dd");
  }
});

watch(() => recipe.value?.id, (recipeId) => {
  if (!dialog.value || recipeId === props.entry?.recipeId) return;
  preparationMode.value = "create";
  preparationId.value = null;
  cookDate.value = format(selectedDate.value, "yyyy-MM-dd");
  cookDinerId.value = null;
});

watch(dialog, (isOpen) => {
  if (isOpen) {
    void initialize();
  }
});
</script>

<style scoped>
.entry-detail {
  position: relative;
  min-height: clamp(320px, 45vh, 520px);
}

/*
  Take the pane out of flow so a long result list scrolls inside it instead of growing the
  dialog, while it still stretches to the height of the settings column beside it.
  The inset matches the v-col gutter padding.
*/
.entry-detail > * {
  position: absolute;
  inset: 12px;
  overflow-y: auto;
}

/* v-switch reserves a taller control than the filter buttons next to it */
.ignore-rules-switch {
  --v-input-control-height: 28px;
  align-self: flex-start;
}
</style>
