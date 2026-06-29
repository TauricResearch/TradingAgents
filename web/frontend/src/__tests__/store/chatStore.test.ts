import { describe, it, expect, beforeEach } from "vitest";
import { useChatStore } from "../../stores/useChatStore";

describe("useChatStore", () => {
  beforeEach(() => {
    useChatStore.getState().clearMessages();
    useChatStore.getState().setOpen(false);
    useChatStore.getState().setLoading(false);
  });

  it("starts with empty state", () => {
    const state = useChatStore.getState();
    expect(state.messages).toEqual([]);
    expect(state.isOpen).toBe(false);
    expect(state.isLoading).toBe(false);
  });

  it("addMessage appends message with generated id and timestamp", () => {
    const before = Date.now();
    const id = useChatStore.getState().addMessage({
      role: "user",
      content: "hello",
    });
    const after = Date.now();

    const messages = useChatStore.getState().messages;
    expect(messages).toHaveLength(1);
    expect(messages[0].id).toBe(id);
    expect(messages[0].role).toBe("user");
    expect(messages[0].content).toBe("hello");
    expect(messages[0].timestamp).toBeGreaterThanOrEqual(before);
    expect(messages[0].timestamp).toBeLessThanOrEqual(after);
  });

  it("addMessage returns unique ids", () => {
    const id1 = useChatStore.getState().addMessage({
      role: "user",
      content: "a",
    });
    const id2 = useChatStore.getState().addMessage({
      role: "user",
      content: "b",
    });
    expect(id1).not.toBe(id2);
  });

  it("addMessage preserves optional fields", () => {
    const toolCalls = [{ id: "tc-1", name: "search", arguments: { q: "test" } }];
    const toolResults = [{ toolCallId: "tc-1", content: "result" }];

    useChatStore.getState().addMessage({
      role: "assistant",
      content: "response",
      toolCalls,
      toolResults,
      isStreaming: true,
    });

    const msg = useChatStore.getState().messages[0];
    expect(msg.toolCalls).toEqual(toolCalls);
    expect(msg.toolResults).toEqual(toolResults);
    expect(msg.isStreaming).toBe(true);
  });

  it("updateMessage applies partial updates", () => {
    const id = useChatStore.getState().addMessage({
      role: "assistant",
      content: "partial",
      isStreaming: true,
    });

    useChatStore.getState().updateMessage(id, {
      content: "complete",
      isStreaming: false,
    });

    const msg = useChatStore.getState().messages[0];
    expect(msg.content).toBe("complete");
    expect(msg.isStreaming).toBe(false);
    expect(msg.role).toBe("assistant");
  });

  it("updateMessage does not affect other messages", () => {
    useChatStore.getState().addMessage({
      role: "user",
      content: "first",
    });
    useChatStore.getState().addMessage({
      role: "user",
      content: "second",
    });

    const firstId = useChatStore.getState().messages[0].id;
    useChatStore.getState().updateMessage(firstId, { content: "updated" });

    expect(useChatStore.getState().messages[0].content).toBe("updated");
    expect(useChatStore.getState().messages[1].content).toBe("second");
  });

  it("toggleChat flips isOpen", () => {
    expect(useChatStore.getState().isOpen).toBe(false);
    useChatStore.getState().toggleChat();
    expect(useChatStore.getState().isOpen).toBe(true);
    useChatStore.getState().toggleChat();
    expect(useChatStore.getState().isOpen).toBe(false);
  });

  it("setOpen sets isOpen to provided value", () => {
    useChatStore.getState().setOpen(true);
    expect(useChatStore.getState().isOpen).toBe(true);
    useChatStore.getState().setOpen(true);
    expect(useChatStore.getState().isOpen).toBe(true);
    useChatStore.getState().setOpen(false);
    expect(useChatStore.getState().isOpen).toBe(false);
  });

  it("setLoading sets isLoading to provided value", () => {
    useChatStore.getState().setLoading(true);
    expect(useChatStore.getState().isLoading).toBe(true);
    useChatStore.getState().setLoading(false);
    expect(useChatStore.getState().isLoading).toBe(false);
  });

  it("clearMessages removes all messages", () => {
    useChatStore.getState().addMessage({ role: "user", content: "a" });
    useChatStore.getState().addMessage({ role: "assistant", content: "b" });
    expect(useChatStore.getState().messages).toHaveLength(2);

    useChatStore.getState().clearMessages();
    expect(useChatStore.getState().messages).toHaveLength(0);
  });

  it("clearMessages does not affect isOpen or isLoading", () => {
    useChatStore.getState().setOpen(true);
    useChatStore.getState().setLoading(true);
    useChatStore.getState().addMessage({ role: "user", content: "a" });

    useChatStore.getState().clearMessages();

    expect(useChatStore.getState().isOpen).toBe(true);
    expect(useChatStore.getState().isLoading).toBe(true);
    expect(useChatStore.getState().messages).toHaveLength(0);
  });
});
