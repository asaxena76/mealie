import type { CarrieContext, CarrieHistory, CarrieSend } from "~/lib/api/types/carrie";
import { useUserApi } from "~/composables/api";

// getRandomValues also works on HTTP LAN deployments, where randomUUID is unavailable.
export function createCarrieRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function useCarrieChat(context: Ref<CarrieContext>, visible: Ref<boolean>) {
  const api = useUserApi().carrie;
  const history = ref<CarrieHistory>({ messages: [], running: false, truncated: false });
  const enabled = ref(false);
  const loading = ref(false);
  const sending = ref(false);
  const error = ref(false);
  const draft = ref("");
  const uncertain = ref(false);
  const conflict = ref(false);
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending: CarrieSend | null = null;
  let loadedRange = "";
  let refreshSequence = 0;
  let disposed = false;

  const rangeKey = computed(() => `${context.value.startDate}/${context.value.endDate}`);

  async function refresh() {
    const current = generation;
    const sequence = ++refreshSequence;
    const requestedContext = { ...context.value };
    const { data } = await api.history(requestedContext);
    if (current !== generation || sequence !== refreshSequence) return;
    if (data) {
      history.value = data;
      error.value = false;
    }
    else {
      error.value = true;
    }
  }

  function schedulePoll() {
    clearTimeout(timer);
    if (disposed || !visible.value || !enabled.value) return;
    const current = generation;
    timer = setTimeout(async () => {
      await refresh();
      if (current === generation) schedulePoll();
    }, history.value.running || sending.value ? 2000 : 10000);
  }

  async function load() {
    const current = ++generation;
    clearTimeout(timer);
    history.value = { messages: [], running: false, truncated: false };
    if (loadedRange !== rangeKey.value) {
      draft.value = "";
      pending = null;
      uncertain.value = false;
      conflict.value = false;
      loadedRange = rangeKey.value;
    }
    if (pending) uncertain.value = true;
    sending.value = false;
    loading.value = true;
    error.value = false;
    const { data } = await api.status();
    if (current !== generation) return;
    enabled.value = Boolean(data?.enabled);
    error.value = !data;
    if (enabled.value) await refresh();
    if (current !== generation) return;
    loading.value = false;
    schedulePoll();
  }

  async function send() {
    if (!enabled.value || loading.value || sending.value || history.value.running || !draft.value.trim()) return;
    const current = generation;
    sending.value = true;
    conflict.value = false;
    // Retain the submission identity and exact payload after uncertain delivery.
    pending ??= {
      ...context.value,
      dinerIds: [...(context.value.dinerIds ?? [])],
      message: draft.value.trim(),
      requestId: createCarrieRequestId(),
      expectedLeafEntryId: history.value.leafEntryId,
    };
    const { data, error: sendError } = await api.send(pending);
    if (current !== generation) return;
    sending.value = false;
    if (data) {
      draft.value = "";
      pending = null;
      uncertain.value = false;
      history.value.running = true;
    }
    else {
      uncertain.value = true;
      // A rejected stale branch was not accepted; allow a new submission after review.
      if (sendError?.response?.status === 409) {
        pending = null;
        uncertain.value = false;
        conflict.value = true;
      }
    }
    await refresh();
    schedulePoll();
  }

  async function stop() {
    const current = generation;
    const { error: stopError } = await api.stop(context.value);
    if (current !== generation) return;
    await refresh();
    if (stopError) error.value = true;
  }

  function discardPending() {
    pending = null;
    uncertain.value = false;
    draft.value = "";
  }

  watch([visible, rangeKey], () => {
    if (visible.value) void load();
    else {
      generation++;
      clearTimeout(timer);
    }
  }, { immediate: true });
  onBeforeUnmount(() => {
    disposed = true;
    generation++;
    clearTimeout(timer);
  });

  return { history, enabled, loading, sending, error, draft, uncertain, conflict, refresh: load, send, stop, discardPending };
}
