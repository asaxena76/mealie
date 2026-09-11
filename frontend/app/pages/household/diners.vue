<template>
  <v-container class="narrow-container">
    <BaseDialog
      v-model="dialogOpen"
      :title="editingId ? $t('household.edit-diner') : $t('household.add-diner')"
      :icon="$globals.icons.accountPlusOutline"
      :submit-disabled="!form.name.trim() || !form.abbreviation.trim()"
      can-submit
      @submit="save"
    >
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="7">
            <v-text-field v-model="form.name" :label="$t('general.name')" maxlength="50" />
          </v-col>
          <v-col cols="6" sm="2">
            <v-text-field v-model="form.abbreviation" :label="$t('household.abbreviation')" maxlength="4" />
          </v-col>
          <v-col cols="6" sm="3">
            <v-text-field v-model="form.emoji" :label="$t('household.emoji')" maxlength="16" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field v-model="form.color" type="color" :label="$t('household.color')" />
          </v-col>
          <v-col cols="12" sm="6">
            <v-switch v-model="form.active" color="primary" :label="$t('household.active-diner')" />
          </v-col>
        </v-row>
      </v-card-text>
    </BaseDialog>

    <BasePageTitle divider>
      <template #title>
        {{ $t("household.diners") }}
      </template>
      {{ $t("household.diners-description") }}
    </BasePageTitle>

    <div class="d-flex justify-end mb-4">
      <BaseButton create @click="openCreate" />
    </div>

    <v-alert v-if="!loading && !diners.length" type="info" variant="tonal">
      {{ $t("household.no-diners") }}
    </v-alert>

    <v-list v-else lines="two">
      <v-list-item v-for="diner in diners" :key="diner.id" :class="{ 'text-medium-emphasis': !diner.active }">
        <template #prepend>
          <v-avatar :color="diner.color || 'primary'" size="42">
            <span v-if="diner.emoji" class="text-h6">{{ diner.emoji }}</span>
            <strong v-else>{{ diner.abbreviation }}</strong>
          </v-avatar>
        </template>
        <v-list-item-title>{{ diner.name }}</v-list-item-title>
        <v-list-item-subtitle>
          {{ diner.abbreviation }} · {{ diner.active ? $t("general.enabled") : $t("general.disabled") }}
        </v-list-item-subtitle>
        <template #append>
          <v-btn icon variant="text" :title="$t('general.edit')" @click="openEdit(diner)">
            <v-icon>{{ $globals.icons.edit }}</v-icon>
          </v-btn>
        </template>
      </v-list-item>
    </v-list>
  </v-container>
</template>

<script setup lang="ts">
import { useHouseholdDiners } from "~/composables/use-household-diners";
import type { CreateDiner, ReadDiner, UpdateDiner } from "~/lib/api/types/meal-plan";

const i18n = useI18n();
const { diners, loading, actions } = useHouseholdDiners();

useSeoMeta({ title: i18n.t("household.diners") });

const dialogOpen = ref(false);
const editingId = ref<string | null>(null);
const form = reactive<CreateDiner>({
  name: "",
  abbreviation: "",
  emoji: "",
  color: "#5C6BC0",
  position: 0,
  active: true,
});

function resetForm() {
  Object.assign(form, {
    name: "",
    abbreviation: "",
    emoji: "",
    color: "#5C6BC0",
    position: diners.value.length,
    active: true,
  });
}

function openCreate() {
  editingId.value = null;
  resetForm();
  dialogOpen.value = true;
}

function openEdit(diner: ReadDiner) {
  editingId.value = diner.id;
  Object.assign(form, {
    name: diner.name,
    abbreviation: diner.abbreviation,
    emoji: diner.emoji ?? "",
    color: diner.color ?? "#5C6BC0",
    position: diner.position ?? 0,
    active: diner.active ?? true,
  });
  dialogOpen.value = true;
}

async function save() {
  if (editingId.value) {
    await actions.update({ ...form, id: editingId.value } as UpdateDiner);
  }
  else {
    await actions.create({ ...form });
  }
  dialogOpen.value = false;
}
</script>
