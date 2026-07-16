import { afterEach, describe, expect, it, vi } from "vitest";

import { desktopNotifyState, maybeNotify } from "../desktopNotify";

type NotificationStub = {
  new (title: string, opts?: { body?: string; tag?: string }): {
    onclick: (() => void) | null;
    close: () => void;
  };
  permission: NotificationPermission;
};

function stubNotification(permission: NotificationPermission) {
  const created: { title: string; body?: string; tag?: string }[] = [];
  class FakeNotification {
    static permission: NotificationPermission = permission;
    onclick: (() => void) | null = null;
    close = vi.fn();
    constructor(title: string, opts?: { body?: string; tag?: string }) {
      created.push({ title, ...opts });
    }
  }
  vi.stubGlobal("Notification", FakeNotification as unknown as NotificationStub);
  return created;
}

function stubHidden(state: DocumentVisibilityState) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => state,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("desktop notifications", () => {
  it("fires only when granted AND the tab is hidden", () => {
    const created = stubNotification("granted");
    stubHidden("hidden");
    expect(maybeNotify("Run complete — XAUUSD", "verdict: SELL", "run-1")).toBe(true);
    expect(created).toEqual([
      { title: "Run complete — XAUUSD", body: "verdict: SELL", tag: "run-1", icon: "/favicon.svg" },
    ]);
  });

  it("stays silent while the dashboard is visible — no double noise", () => {
    const created = stubNotification("granted");
    stubHidden("visible");
    expect(maybeNotify("t", "b", "tag")).toBe(false);
    expect(created).toEqual([]);
  });

  it("never fires without permission", () => {
    const created = stubNotification("default");
    stubHidden("hidden");
    expect(maybeNotify("t", "b", "tag")).toBe(false);
    expect(created).toEqual([]);
  });

  it("reports state, including unsupported browsers", () => {
    stubNotification("denied");
    expect(desktopNotifyState()).toBe("denied");
    vi.unstubAllGlobals();
    vi.stubGlobal("Notification", undefined);
    expect(desktopNotifyState()).toBe("unsupported");
  });
});
