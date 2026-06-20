import "@testing-library/jest-dom/vitest";

// recharts' ResponsiveContainer uses ResizeObserver, which jsdom does
// not provide. Polyfill a no-op observer so the chart can mount in tests.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  } as unknown as typeof ResizeObserver;
}

// jsdom does not implement scrollIntoView; stub it unconditionally
if (typeof Element !== "undefined") {
  Element.prototype.scrollIntoView = function () {};
}

// recharts' ResponsiveContainer also reads getBoundingClientRect to size
// the chart; jsdom's default returns {0,0}, which recharts rejects. Stub
// a non-zero rect unconditionally so the surface mounts and reference
// elements render.
if (typeof HTMLElement !== "undefined") {
  HTMLElement.prototype.getBoundingClientRect = function (): DOMRect {
    return {
      width: 800, height: 600, top: 0, left: 0, bottom: 600, right: 800, x: 0, y: 0,
      toJSON() { return this; },
    } as DOMRect;
  };
}
