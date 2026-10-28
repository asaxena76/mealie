<template>
  <v-navigation-drawer
    v-model="open"
    location="right"
    temporary
    :width="$vuetify.display.xs ? $vuetify.display.width : width"
  >
    <div class="d-flex flex-column h-100">
      <div class="d-flex align-center pa-3 ga-2">
        <h2 class="text-h6">
          {{ $t("carrie.stock-title") }}
        </h2>
        <v-chip size="small">
          {{ $t(isDevelopment ? "carrie.stock-dev" : "carrie.read-only") }}
        </v-chip>
        <v-spacer />
        <v-btn icon variant="text" :aria-label="$t('general.close')" @click="open = false">
          <v-icon>{{ $globals.icons.close }}</v-icon>
        </v-btn>
      </div>
      <div class="px-3 pb-2">
        <div class="text-body-2">
          {{ context.startDate }} – {{ context.endDate }} · {{ dinerLabel }}
        </div>
        <div class="text-caption">
          {{ $t(context.includeCooking ? "carrie.stock-cooking-on" : "carrie.stock-cooking-off") }}
        </div>
        <div class="d-flex align-center ga-2 mt-2">
          <v-btn size="small" color="primary" :disabled="!documentId || !sessionKey" @click="share">
            {{ $t("carrie.stock-share") }}
          </v-btn>
          <span class="text-caption" role="status">{{ $t(shared ? "carrie.stock-shared" : "carrie.stock-not-shared") }}</span>
        </div>
        <v-slider
          v-if="!$vuetify.display.xs"
          v-model="width"
          :label="$t('carrie.stock-width')"
          :min="480"
          :max="Math.max(480, $vuetify.display.width - 48)"
          :step="20"
          hide-details
          density="compact"
        />
      </div>
      <v-alert v-if="error" type="warning" variant="tonal" class="ma-3">
        {{ $t("carrie.stock-unavailable") }}
        <v-btn size="small" variant="text" @click="launch">
          {{ $t("carrie.refresh") }}
        </v-btn>
      </v-alert>
      <v-progress-linear v-if="loading" indeterminate />
      <iframe
        v-if="src"
        ref="frame"
        :src="src"
        :title="$t('carrie.stock-title')"
        class="carrie-stock-frame"
        sandbox="allow-scripts allow-same-origin allow-forms"
        referrerpolicy="no-referrer"
      />
    </div>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import type { CarrieContext } from "~/lib/api/types/carrie";

const open = defineModel<boolean>({ default: false });
const props = defineProps<{ context: CarrieContext; dinerLabel: string; endpoint: string; agentId: string }>();
const auth = useAuthBackend();
const isDevelopment = import.meta.dev;
const target = new URL(props.endpoint, window.location.origin);
const origin = target.origin;
const prefix = target.pathname.replace(/\/$/, "");
const embedEndpoint = origin + prefix;
const initialPath = `${prefix}/new?agent=${encodeURIComponent(props.agentId)}`;
const frame = ref<HTMLIFrameElement>();
const src = ref("");
const width = ref(1000);
const loading = ref(false);
const error = ref(false);
const shared = ref(false);
const documentId = ref("");
const sessionKey = ref<string | null>(null);
const revision = computed(() => JSON.stringify(props.context));
let generation = 0;
let lease = "";
let lastPath = initialPath;
let readyTimer: ReturnType<typeof setTimeout> | undefined;

function post(type: string, extra = {}) {
  frame.value?.contentWindow?.postMessage({
    source: "mealie-planner", version: 1, type, documentId: documentId.value, ...extra,
  }, origin);
}

function receive(event: MessageEvent) {
  if (event.origin !== origin || event.source !== frame.value?.contentWindow) return;
  const data = event.data;
  if (!data || data.source !== "mealie-stock-ui" || data.version !== 1 || typeof data.documentId !== "string") return;
  if (data.type === "ready") {
    clearTimeout(readyTimer);
    documentId.value = data.documentId;
    post("initialize", { lease });
    shared.value = false;
    loading.value = false;
    error.value = false;
  }
  if (data.documentId !== documentId.value) return;
  if (typeof data.path === "string" && data.path.startsWith(`${prefix}/chat/${props.agentId}/`)) lastPath = data.path;
  if (data.path === `${prefix}/new`) lastPath = initialPath;
  sessionKey.value = typeof data.sessionKey === "string" ? data.sessionKey : null;
  if (["session", "cleared", "context-needed"].includes(data.type)) shared.value = false;
  if (data.type === "shared") shared.value = data.revision === revision.value;
}

function share() {
  post("share", { sessionKey: sessionKey.value, context: JSON.parse(revision.value), revision: revision.value });
}

async function launch() {
  revoke();
  const current = ++generation;
  src.value = "";
  documentId.value = "";
  sessionKey.value = null;
  shared.value = false;
  error.value = false;
  loading.value = true;
  clearTimeout(readyTimer);
  try {
    if (!auth.token.value) throw new Error("Mealie login required");
    if (!import.meta.dev && (origin !== window.location.origin || prefix !== "/carrie")) throw new Error("Invalid Carrie endpoint");
    const response = await fetch(`${embedEndpoint}/__mealie__/auth`, {
      method: "POST", credentials: "same-origin",
      headers: { Authorization: `Bearer ${auth.token.value}` },
      signal: AbortSignal.timeout(15000),
    });
    if (!response.ok) throw new Error("Stock UI authentication failed");
    const result = await response.json();
    if (current !== generation || !open.value) {
      revoke(result.lease);
      return;
    }
    lease = result.lease;
    src.value = `${origin}${lastPath}`;
    readyTimer = setTimeout(() => { loading.value = false; error.value = true; }, 20000);
  }
  catch {
    if (current !== generation) return;
    loading.value = false;
    error.value = true;
  }
}

function revoke(key = lease) {
  if (key) void fetch(`${embedEndpoint}/__mealie__/auth`, {
    method: "DELETE", headers: { "X-Mealie-Lease": key }, keepalive: true,
  }).catch(() => {});
  if (key === lease) lease = "";
}

watch(revision, () => { shared.value = false; post("clear"); });
watch(open, (visible) => {
  if (visible) void launch();
  else {
    generation++;
    clearTimeout(readyTimer);
    src.value = "";
    documentId.value = "";
    shared.value = false;
    revoke();
  }
});
watch(auth.token, () => {
  open.value = false;
  revoke();
});
onMounted(() => window.addEventListener("message", receive));
onBeforeUnmount(() => {
  generation++;
  clearTimeout(readyTimer);
  revoke();
  window.removeEventListener("message", receive);
});
</script>

<style scoped>
.carrie-stock-frame {
  flex: 1;
  width: 100%;
  min-height: 0;
  border: 0;
}
</style>
