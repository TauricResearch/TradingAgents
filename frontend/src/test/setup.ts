import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Auto-cleanup the DOM between tests so `render` from one test does not leak
// into the next (otherwise getByRole finds duplicated elements).
afterEach(() => {
  cleanup();
});