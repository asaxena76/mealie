import { mount, flushPromises } from "@vue/test-utils";
import { defineComponent, ref } from "vue";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { createCarrieRequestId, useCarrieChat } from "../use-carrie-chat";
import type { CarrieContext } from "~/lib/api/types/carrie";

const api = vi.hoisted(() => ({ status: vi.fn(), history: vi.fn(), send: vi.fn(), stop: vi.fn() }));
vi.mock("~/composables/api", () => ({ useUserApi: () => ({ carrie: api }) }));

const context = ref<CarrieContext>({ startDate: "2026-11-02", endDate: "2026-11-08", dinerIds: [] });
const visible = ref(true);
let chat: ReturnType<typeof useCarrieChat>;
let wrapper: ReturnType<typeof mount>;

beforeEach(async () => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  context.value = { startDate: "2026-11-02", endDate: "2026-11-08", dinerIds: [] };
  visible.value = true;
  api.status.mockResolvedValue({ data: { enabled: true } });
  api.history.mockResolvedValue({ data: { messages: [], running: false, leafEntryId: "leaf-1" } });
  api.send.mockResolvedValue({ data: { runId: "run-1" } });
  api.stop.mockResolvedValue({ error: null });
  wrapper = mount(defineComponent({ setup() { chat = useCarrieChat(context, visible); return () => null; } }));
  await flushPromises();
});

afterEach(() => { wrapper.unmount(); vi.useRealTimers(); });

describe("Carrie chat", () => {
  test("creates UUIDs without requiring secure-context randomUUID", () => {
    expect(createCarrieRequestId()).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(createCarrieRequestId()).not.toEqual(createCarrieRequestId());
  });

  test("stale submissions keep the draft and require review", async () => {
    api.send.mockResolvedValueOnce({ data: null, error: { response: { status: 409 } } });
    chat.draft.value = "Review this week";
    await chat.send();
    expect(chat.conflict.value).toBe(true);
    expect(chat.uncertain.value).toBe(false);
    expect(chat.draft.value).toBe("Review this week");
  });
  test("sends current filters and the last observed conversation leaf", async () => {
    context.value.dinerIds = ["fictional-diner"];
    chat.draft.value = "Review this week";
    await chat.send();
    expect(api.send).toHaveBeenCalledWith(expect.objectContaining({
      dinerIds: ["fictional-diner"], expectedLeafEntryId: "leaf-1", message: "Review this week",
    }));
    expect(chat.draft.value).toBe("");
  });

  test("uncertain retries preserve identity across panel close/reopen", async () => {
    api.send.mockResolvedValueOnce({ data: null });
    chat.draft.value = "Review this week";
    await chat.send();
    const submission = api.send.mock.calls[0][0];
    expect(chat.uncertain.value).toBe(true);
    visible.value = false;
    await flushPromises();
    visible.value = true;
    await flushPromises();
    await chat.send();
    expect(api.send.mock.calls[1][0]).toEqual(submission);
  });

  test("ignores history returned after switching weeks", async () => {
    let resolveOld: (value: unknown) => void = () => {};
    api.history.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    const oldRefresh = chat.refresh();
    await flushPromises();
    context.value = { startDate: "2026-11-09", endDate: "2026-11-15" };
    await flushPromises();
    resolveOld({ data: { messages: [{ id: "old", role: "assistant", text: "Old week" }], running: false } });
    await oldRefresh;
    expect(chat.history.value.messages).toEqual([]);
  });

  test("does not poll while closed and stops only the displayed conversation", async () => {
    await chat.stop();
    expect(api.stop).toHaveBeenCalledWith(context.value);
    visible.value = false;
    await flushPromises();
    api.history.mockClear();
    await vi.advanceTimersByTimeAsync(30000);
    expect(api.history).not.toHaveBeenCalled();
  });

  test("an in-flight poll cannot restart polling after unmount", async () => {
    let finish: (value: unknown) => void = () => {};
    api.history.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    vi.advanceTimersByTime(10000);
    wrapper.unmount();
    finish({ data: { messages: [], running: false } });
    await flushPromises();
    api.history.mockClear();
    await vi.advanceTimersByTimeAsync(30000);
    expect(api.history).not.toHaveBeenCalled();
  });
});
