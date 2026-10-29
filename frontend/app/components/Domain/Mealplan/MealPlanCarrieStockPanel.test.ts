import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { ref } from "vue";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import MealPlanCarrieStockPanel from "./MealPlanCarrieStockPanel.vue";

const context = { startDate: "2026-11-02", endDate: "2026-11-08", dinerIds: [], includeCooking: true };
let wrapper: VueWrapper;
let frame: HTMLIFrameElement;
let sent: ReturnType<typeof vi.spyOn>;

function receive(type: string, extra = {}, origin = window.location.origin, source = frame.contentWindow) {
  window.dispatchEvent(new MessageEvent("message", { origin, source, data: {
    source: "mealie-stock-ui", version: 1, documentId: "document-1", type,
    sessionKey: "@new", path: "/carrie/new", ...extra,
  } }));
}

beforeEach(async () => {
  vi.stubGlobal("useAuthBackend", () => ({ token: ref("fictional-token") }));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ lease: "fictional-lease" }) }));
  wrapper = mount(MealPlanCarrieStockPanel, {
    props: { modelValue: false, context, dinerLabel: "Everyone", endpoint: "/carrie", agentId: "carrie" },
    global: {
      mocks: { $vuetify: { display: { xs: false, width: 1200 } }, $globals: { icons: { close: "close" } } },
      stubs: Object.fromEntries(["VNavigationDrawer", "VChip", "VSpacer", "VBtn", "VIcon", "VSlider", "VAlert", "VProgressLinear"]
        .map(name => [name, { template: "<div><slot /></div>" }])),
    },
    attachTo: document.body,
  });
  await wrapper.setProps({ modelValue: true });
  await flushPromises();
  frame = wrapper.get("iframe").element as HTMLIFrameElement;
  sent = vi.spyOn(frame.contentWindow!, "postMessage");
});

afterEach(() => { wrapper.unmount(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test("opening and changing threads automatically attach current view", () => {
  receive("ready");
  expect(sent).toHaveBeenCalledWith(expect.objectContaining({ type: "initialize", lease: "fictional-lease" }), window.location.origin);
  expect(sent).toHaveBeenLastCalledWith(expect.objectContaining({ type: "share", sessionKey: "@new", context }), window.location.origin);
  receive("session", { sessionKey: "agent:carrie:second", path: "/carrie/chat/carrie/second" });
  expect(sent).toHaveBeenLastCalledWith(expect.objectContaining({ type: "share", sessionKey: "agent:carrie:second", context }), window.location.origin);
});

test("changed dates and filters replace context without a manual action", async () => {
  receive("ready");
  const changed = { ...context, startDate: "2026-11-09", endDate: "2026-11-15", dinerIds: ["fictional-diner"], includeCooking: false };
  await wrapper.setProps({ context: changed });
  expect(sent).toHaveBeenLastCalledWith(expect.objectContaining({ type: "share", context: changed }), window.location.origin);
  // A late acknowledgement of the old view cannot mark it synchronized.
  receive("shared", { revision: JSON.stringify(context) });
  expect(sent).toHaveBeenLastCalledWith(expect.objectContaining({ type: "share", context: changed }), window.location.origin);
});

test("foreign frames and stale documents cannot solicit context", () => {
  receive("ready", {}, "https://foreign.example");
  receive("ready", {}, window.location.origin, window);
  expect(sent).not.toHaveBeenCalled();
  receive("ready");
  sent.mockClear();
  receive("session", { documentId: "stale-document" });
  expect(sent).not.toHaveBeenCalled();
});
