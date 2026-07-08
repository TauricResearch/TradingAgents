import { expect, test } from "@playwright/test";

const TOKEN = "e2e-token";

async function unlock(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByTestId("token-input").fill(TOKEN);
  await page.getByTestId("token-submit").click();
  await expect(page.getByTestId("conn-state")).toBeVisible({ timeout: 15_000 });
}

test.describe("auth", () => {
  test("token gate: wrong token stays locked, right token unlocks", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByTestId("token-input").fill("wrong");
    await page.getByTestId("token-submit").click();
    await expect(page.getByTestId("token-input")).toBeVisible();
    await page.getByTestId("token-input").fill(TOKEN);
    await page.getByTestId("token-submit").click();
    await expect(page.getByTestId("decision-card")).toBeVisible({
      timeout: 15_000,
    });
  });

  test("api rejects unauthenticated requests", async ({ request }) => {
    const denied = await request.get("/api/overview");
    expect(denied.status()).toBe(401);
    const ok = await request.get("/api/overview", {
      headers: { "X-API-Key": TOKEN },
    });
    expect(ok.status()).toBe(200);
  });
});

test.describe("terminal", () => {
  test.beforeEach(async ({ page }) => unlock(page));

  test("home answers the 5-second questions", async ({ page }) => {
    // safe? — risk badge; AI stance? — decision card; P&L? — snapshot
    await expect(page.getByTestId("risk-badge")).toContainText(/risk: OK|KILL|BREAKER/);
    await expect(page.getByTestId("decision-card")).toContainText("BUY");
    await expect(page.getByTestId("decision-card")).toContainText("confidence");
    await expect(page.getByTestId("invalidation")).toBeVisible();
    await expect(page.getByText("Total P&L").first()).toBeVisible();
  });

  test("decision center shows debate, gates, and leaderboard", async ({
    page,
  }) => {
    await page.goto("/decisions");
    await expect(page.getByTestId("gate-waterfall")).toBeVisible();
    await expect(page.getByTestId("debate-timeline")).toBeVisible();
    await expect(page.getByTestId("agent-leaderboard")).toBeVisible();
    await expect(page.getByTestId("debate-timeline")).toContainText("judge");
  });

  test("run pinning survives navigation", async ({ page }) => {
    await page.goto("/decisions");
    const first = page.getByTestId("run-rail").locator("button").first();
    await first.click();
    await expect(page).toHaveURL(/\/decisions\/[0-9a-f-]+/);
    const url = page.url();
    await page.reload();
    expect(page.url()).toBe(url);
    await expect(page.getByTestId("debate-timeline")).toBeVisible();
  });

  test("workspace renders a chart for gold", async ({ page }) => {
    await page.goto("/trade/XAUUSD");
    await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText("EOD data")).toBeVisible();
  });

  test("portfolio links trades to reasoning and exports CSV", async ({
    page,
  }) => {
    await page.goto("/portfolio");
    await expect(page.getByTestId("trades-table")).toBeVisible();
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: /CSV/ }).click();
    const file = await download;
    expect(file.suggestedFilename()).toMatch(/journal-\d+\.csv/);
  });

  test("command palette navigates", async ({ page, isMobile }) => {
    test.skip(isMobile, "palette is keyboard-driven");
    await page.keyboard.press("ControlOrMeta+k");
    await page.getByPlaceholder(/Search commands/).fill("Portfolio");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/portfolio/);
  });

  test("keyboard chords: g d goes to decisions", async ({ page, isMobile }) => {
    test.skip(isMobile, "keyboard chords are desktop UX");
    await page.keyboard.press("g");
    await page.keyboard.press("d");
    await expect(page).toHaveURL(/\/decisions/);
  });

  test("intel shows honest feed coverage", async ({ page }) => {
    await page.goto("/intel");
    // first load may take the full vendor deadline (~10s) when egress
    // to feeds is blocked — the page must still render, with gaps disclosed
    await expect(page.getByText("Not subscribed")).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Coinglass")).toBeVisible();
  });

  test("sse stream is reachable with the session cookie", async ({ page }) => {
    const status = await page.evaluate(async () => {
      // fetch resolves on response headers; cancel the infinite body
      const response = await fetch("/api/stream", {
        headers: { Accept: "text/event-stream" },
      });
      const type = response.headers.get("content-type") ?? "";
      response.body?.cancel();
      return { ok: response.ok, type };
    });
    expect(status.ok).toBe(true);
    expect(status.type).toContain("text/event-stream");
  });
});
