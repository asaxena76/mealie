import { useUserApi } from "~/composables/api";
import type { CreateDiner, ReadDiner, UpdateDiner } from "~/lib/api/types/meal-plan";

const diners = ref<ReadDiner[]>([]);
const loading = ref(false);
let loaded = false;

export function resetHouseholdDiners() {
  diners.value = [];
  loaded = false;
}

export function useHouseholdDiners() {
  const api = useUserApi();

  async function refresh() {
    loading.value = true;
    const { data } = await api.householdDiners.getAll(1, -1, {
      orderBy: "position,name",
      orderDirection: "asc",
    });
    diners.value = data?.items ?? [];
    loaded = true;
    loading.value = false;
  }

  async function ensureLoaded() {
    if (!loaded && !loading.value) {
      await refresh();
    }
  }

  async function create(payload: CreateDiner) {
    await api.householdDiners.createOne(payload);
    await refresh();
  }

  async function update(payload: UpdateDiner) {
    await api.householdDiners.updateOne(payload.id, payload);
    await refresh();
  }

  async function remove(id: string) {
    await api.householdDiners.deleteOne(id);
    await refresh();
  }

  void ensureLoaded();

  return {
    diners,
    activeDiners: computed(() => diners.value.filter(diner => diner.active)),
    loading,
    actions: { refresh, create, update, remove },
  };
}
