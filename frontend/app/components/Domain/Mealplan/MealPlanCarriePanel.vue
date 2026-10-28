<template>
  <v-navigation-drawer
    v-model="open"
    location="right"
    temporary
    :width="$vuetify.display.xs ? $vuetify.display.width : 460"
  >
    <div class="d-flex flex-column h-100">
      <div class="d-flex align-center pa-4 ga-2">
        <v-icon color="primary">
          {{ $globals.icons.chefHat }}
        </v-icon>
        <h2 class="text-h6">
          {{ $t("carrie.title") }}
        </h2>
        <v-spacer />
        <v-btn icon variant="text" :aria-label="$t('general.close')" @click="open = false">
          <v-icon>{{ $globals.icons.close }}</v-icon>
        </v-btn>
      </div>
      <div class="px-4 pb-3 text-body-2">
        <div>{{ context.startDate }} – {{ context.endDate }}</div>
        <div class="text-medium-emphasis">
          {{ dinerLabel }}
        </div>
        <v-chip size="x-small" class="mt-2">
          {{ $t("carrie.read-only") }}
        </v-chip>
      </div>
      <v-divider />
      <v-progress-linear v-if="loading" indeterminate color="primary" />
      <div ref="transcript" class="flex-grow-1 overflow-y-auto pa-4" role="log" :aria-label="$t('carrie.conversation')" aria-live="polite">
        <v-alert v-if="!loading && !enabled && !error" type="info" variant="tonal">
          {{ $t("carrie.not-configured") }}
        </v-alert>
        <v-alert v-if="error" type="warning" variant="tonal" class="mb-3">
          {{ $t("carrie.connection-error") }}
          <v-btn variant="text" size="small" @click="refresh">
            {{ $t("carrie.refresh") }}
          </v-btn>
        </v-alert>
        <p v-if="history.truncated" class="text-caption mb-3">
          {{ $t("carrie.recent-history") }}
        </p>
        <div v-if="enabled && !loading && !history.messages.length && !error" class="text-body-2 text-medium-emphasis">
          <p class="mb-4">
            {{ $t("carrie.welcome") }}
          </p>
          <v-btn variant="tonal" color="primary" size="small" @click="draft = $t('carrie.review-prompt')">
            {{ $t("carrie.review-week") }}
          </v-btn>
        </div>
        <div v-for="message in history.messages" :key="message.id" class="mb-4">
          <div class="text-caption font-weight-bold mb-1">
            {{ message.role === "user" ? $t("carrie.you") : $t("carrie.title") }}
          </div>
          <div class="pa-3 rounded text-body-2 carrie-message" :class="message.role === 'user' ? 'bg-surface-light' : ''">
            {{ message.text }}
          </div>
        </div>
        <div v-if="history.running || sending" class="d-flex align-center ga-2 text-body-2" role="status">
          <v-progress-circular indeterminate size="16" width="2" />
          {{ $t("carrie.working") }}
          <v-btn v-if="history.running" size="small" variant="text" @click="stop">
            {{ $t("carrie.stop") }}
          </v-btn>
        </div>
      </div>
      <v-divider />
      <form class="pa-4" @submit.prevent="send">
        <v-alert v-if="conflict" type="warning" variant="tonal" class="mb-3" density="compact">
          {{ $t("carrie.conversation-changed") }}
        </v-alert>
        <v-alert v-if="uncertain" type="warning" variant="tonal" class="mb-3" density="compact">
          {{ $t("carrie.delivery-uncertain") }}
          <v-btn size="small" variant="text" @click="discardPending">
            {{ $t("carrie.clear-draft") }}
          </v-btn>
        </v-alert>
        <v-textarea
          v-model="draft"
          :label="$t('carrie.message-label')"
          :disabled="!enabled || loading || sending || uncertain"
          rows="2"
          auto-grow
          max-rows="6"
          maxlength="8000"
          hide-details
          @keydown.ctrl.enter.prevent="send"
          @keydown.meta.enter.prevent="send"
        />
        <div class="d-flex justify-end mt-2">
          <v-btn type="submit" color="primary" :loading="sending" :disabled="!enabled || loading || history.running || !draft.trim()">
            {{ uncertain ? $t("carrie.retry") : $t("carrie.send") }}
          </v-btn>
        </div>
      </form>
    </div>
  </v-navigation-drawer>
</template>

<script setup lang="ts">
import type { CarrieContext } from "~/lib/api/types/carrie";

const open = defineModel<boolean>({ default: false });
const props = defineProps<{ context: CarrieContext; dinerLabel: string }>();
const context = toRef(props, "context");
const { history, enabled, loading, sending, error, draft, uncertain, conflict, refresh, send, stop, discardPending } = useCarrieChat(context, open);
const transcript = ref<HTMLElement>();
watch(() => history.value.messages.length, async () => {
  await nextTick();
  transcript.value?.scrollTo({ top: transcript.value.scrollHeight, behavior: "smooth" });
});
</script>

<style scoped>
.carrie-message {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
