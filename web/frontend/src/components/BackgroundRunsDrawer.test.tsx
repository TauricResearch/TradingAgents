import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BackgroundRunsDrawer } from "./BackgroundRunsDrawer";
import * as api from "../lib/api";

function renderDrawer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <BackgroundRunsDrawer focusedTicker="NVDA" />
    </QueryClientProvider>
  );
}

describe("BackgroundRunsDrawer form", () => {
  it("renders the focused ticker preselected", () => {
    renderDrawer();
    const select = screen.getByLabelText(/ticker/i) as HTMLSelectElement;
    expect(select.value).toBe("NVDA");
  });

  it("calls startBackgroundRun on submit and shows a 422 error inline on failure", async () => {
    const spy = vi.spyOn(api, "startBackgroundRun").mockRejectedValue(
      new Error("validation: date_to cannot be in the future")
    );
    renderDrawer();
    await userEvent.click(screen.getByRole("button", { name: /start/i }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText(/validation: date_to cannot be in the future/)).toBeInTheDocument());
  });
});
