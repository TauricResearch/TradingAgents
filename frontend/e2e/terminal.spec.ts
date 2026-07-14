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
    await expect(page.getByTestId("risk-badge")).toContainText(/risk OK|KILL|BREAKER|monitor/);
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

  // regression: unmounting a page disposed the lightweight-charts instance
  // before dependent effect cleanups ran; unguarded removeSeries/unsubscribe
  // calls threw ("Object is disposed" / "Value is undefined") and the
  // workspace crashed to its error boundary on the return visit
  test("workspace survives trade → portfolio → trade SPA navigation", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "keyboard chords are desktop UX");
    const pageErrors: string[] = [];
    page.on("pageerror", (err) => pageErrors.push(String(err)));

    // default symbol is BTC-USD (no seeded chart data); x toggles to XAUUSD
    await page.keyboard.press("x");
    await page.keyboard.press("g");
    await page.keyboard.press("t");
    await expect(page).toHaveURL(/\/trade\/XAUUSD/);
    const canvas = page.getByTestId("price-chart").locator("canvas").first();
    await expect(canvas).toBeVisible({ timeout: 20_000 });

    // portfolio must mount (and later unmount) its EquityCurve chart —
    // that unmount is what used to throw
    await page.keyboard.press("g");
    await page.keyboard.press("p");
    await expect(page.getByTestId("equity-curve")).toBeVisible({
      timeout: 20_000,
    });

    await page.keyboard.press("g");
    await page.keyboard.press("t");
    await expect(canvas).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/failed to render/)).toHaveCount(0);
    expect(pageErrors).toEqual([]);
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

test.describe("v2 features", () => {
  test.beforeEach(async ({ page }) => unlock(page));

  test("replay mode isolates history from live", async ({ page }) => {
    await page.goto("/trade/XAUUSD");
    await expect(
      page.getByTestId("price-chart").locator("canvas").first(),
    ).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: /Replay/ }).click();
    await expect(page.getByTestId("replay-badge")).toContainText("REPLAY");
    await expect(page.getByText("live ticks suspended")).toBeVisible();
    await page.getByRole("button", { name: "Exit replay" }).click();
    await expect(page.getByTestId("replay-badge")).toHaveCount(0);
  });

  test("indicator picker adds a pane", async ({ page }) => {
    await page.goto("/trade/XAUUSD");
    await expect(
      page.getByTestId("price-chart").locator("canvas").first(),
    ).toBeVisible({ timeout: 20_000 });
    const before = await page
      .getByTestId("price-chart")
      .locator("table canvas")
      .count();
    await page.getByTestId("indicator-picker").click();
    await page.getByText("RSI 14").click();
    await page.keyboard.press("Escape");
    await expect
      .poll(
        async () =>
          page.getByTestId("price-chart").locator("table canvas").count(),
        { timeout: 15_000 },
      )
      .toBeGreaterThan(before);
  });

  test("watchlist add and remove persists", async ({ page, isMobile }) => {
    // per-project symbol: both projects share one server + prefs store
    const symbol = isMobile ? "SILVER" : "DXY";
    await page.goto("/");
    const panel = page.getByTestId("watchlist-panel");
    await expect(panel).toBeVisible();
    await panel.getByLabel("Add symbol to watchlist").fill(symbol);
    await panel.getByRole("button", { name: /Add/ }).click();
    await expect(panel.getByRole("link", { name: symbol })).toBeVisible();
    await page.reload();
    await expect(
      page.getByTestId("watchlist-panel").getByRole("link", { name: symbol }),
    ).toBeVisible({ timeout: 15_000 });
    await page
      .getByTestId("watchlist-panel")
      .getByLabel(`remove ${symbol}`)
      .click();
    await expect(
      page.getByTestId("watchlist-panel").getByRole("link", { name: symbol }),
    ).toHaveCount(0);
  });

  test("correlation matrix renders or discloses gaps", async ({ page }) => {
    await page.goto("/intel");
    // either a matrix with data or an honest not-enough-data state
    await expect(
      page
        .getByTestId("correlation-matrix")
        .or(page.getByText("Not enough overlapping data")),
    ).toBeVisible({ timeout: 30_000 });
  });

  test("saved views round-trip through palette and settings", async ({
    page,
    isMobile,
  }) => {
    // desktop-only also avoids racing the shared prefs store
    test.skip(isMobile, "palette is keyboard-driven");
    await page.goto("/portfolio");
    await page.keyboard.press("ControlOrMeta+k");
    await page.getByPlaceholder(/Search commands/).fill("Save current view");
    await page.keyboard.press("Enter");
    await page.goto("/settings");
    const views = page.getByTestId("saved-views");
    await expect(views).toContainText("portfolio");
    await views.getByRole("button").first().click();
    await expect(page.getByTestId("saved-views")).toHaveCount(0);
  });
});

test.describe("v3 drawing tools", () => {
  test.beforeEach(async ({ page }) => unlock(page));

  /** Place a two-point drawing like a human: arm the tool, click twice,
   * and if nothing landed (slow CI runners can swallow taps during
   * chart layout settle) cancel and try again. */
  async function placeTwoPoints(
    page: import("@playwright/test").Page,
    tool: RegExp,
    points: [number, number][],
  ) {
    const chart = page.getByTestId("price-chart");
    const before = Number(await chart.getAttribute("data-drawings"));
    for (let attempt = 0; attempt < 3; attempt++) {
      await page.getByRole("button", { name: tool }).click();
      const box = (await chart.boundingBox())!;
      for (const [fx, fy] of points) {
        await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
        await page.waitForTimeout(650);
      }
      const after = Number(await chart.getAttribute("data-drawings"));
      if (after > before) return;
      await page.keyboard.press("Escape"); // reset any half-placed state
      await page.waitForTimeout(400);
    }
  }

  test("trendline: draw, persist across reload, erase", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "drawing tools are desktop-only by design");
    await page.goto("/trade/XAUUSD");
    const chart = page.getByTestId("price-chart");
    await expect(chart.locator("canvas").first()).toBeVisible({
      timeout: 20_000,
    });
    await expect(chart).toHaveAttribute("data-drawings", "0");

    await page.waitForTimeout(800); // let the chart finish its layout settle
    await placeTwoPoints(page, /Trendline/, [[0.3, 0.4], [0.6, 0.55]]);
    await expect(chart).toHaveAttribute("data-drawings", "1");

    await page.reload();
    await expect(
      page.getByTestId("price-chart"),
    ).toHaveAttribute("data-drawings", "1", { timeout: 20_000 });

    await page.getByRole("button", { name: /Erase/ }).click();
    const box2 = (await page.getByTestId("price-chart").boundingBox())!;
    // click the segment midpoint
    await page.mouse.click(box2.x + box2.width * 0.45, box2.y + box2.height * 0.475);
    await expect(
      page.getByTestId("price-chart"),
    ).toHaveAttribute("data-drawings", "0");
  });

  test("fib places with two clicks; Esc cancels in-progress", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "drawing tools are desktop-only by design");
    await page.goto("/trade/XAUUSD");
    const chart = page.getByTestId("price-chart");
    await expect(chart.locator("canvas").first()).toBeVisible({
      timeout: 20_000,
    });
    const box = (await chart.boundingBox())!;

    // start a fib, then cancel — nothing persists
    await page.getByRole("button", { name: /Fib retracement/ }).click();
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.3);
    await page.keyboard.press("Escape");
    await expect(chart).toHaveAttribute("data-drawings", "0");

    // place a full fib
    await placeTwoPoints(page, /Fib retracement/, [[0.3, 0.3], [0.6, 0.7]]);
    await expect(chart).toHaveAttribute("data-drawings", "1");

    // clear all
    await page.getByRole("button", { name: /Clear all drawings/ }).click();
    await expect(chart).toHaveAttribute("data-drawings", "0");
  });
});

test.describe("v7 on-demand pipeline", () => {
  test("run dialog triggers a run that lands in the rail", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "run rail is a desktop surface");
    await unlock(page);
    await page.goto("/decisions");

    const rail = page.getByTestId("run-rail");
    await expect(rail.locator("li").first()).toBeVisible();
    const before = await rail.locator("li").count();

    await page.getByTestId("run-pipeline-open").click();
    await expect(page.getByTestId("pipeline-start")).toBeVisible();
    await expect(page.getByText(/\$0\.10/)).toBeVisible(); // honest cost note
    await page.getByTestId("pipeline-start").click();

    // fake-LLM run completes fast; SSE `run` refetches the rail
    await expect(async () => {
      expect(await rail.locator("li").count()).toBe(before + 1);
    }).toPass({ timeout: 20_000 });

    // newest run carries its timeframe badge
    await page.keyboard.press("Escape");
    await expect(rail.locator("li").first()).toContainText("1d");
  });
});

test.describe("v-golive Phase 4 arming", () => {
  test("decision board + per-symbol ticket survive symbol mismatch", async ({
    page,
  }) => {
    // Home: board with a hero and the second symbol's compact slot (G1)
    await expect(page.getByTestId("decision-board")).toBeVisible();
    // Trade page for the demo's traded symbol shows a ticket, and the
    // per-symbol endpoint answers for the OTHER symbol without lying
    await page.goto("/trade/XAUUSD");
    await expect(
      page.getByTestId("decision-card").or(
        page.getByText("No decision yet for XAUUSD")),
    ).toBeVisible({ timeout: 10_000 });

    const gold = await page.request.get(
      "/api/recommendation/latest?symbol=XAUUSD",
      { headers: { "X-API-Key": TOKEN } });
    expect(gold.status()).toBe(200);
  });

  test("open positions expose entry/mark/unrealized honestly", async ({
    page,
  }) => {
    const status = await page.request.get("/api/status",
      { headers: { "X-API-Key": TOKEN } });
    const body = await status.json();
    if ((body.open_positions ?? []).length > 0) {
      const pos = body.open_positions[0];
      expect(pos).toHaveProperty("entry_price");
      expect(pos).toHaveProperty("mark_source");
      await page.goto(`/trade/${pos.symbol}`);
      await expect(
        page.getByTestId("position-unrealized").first(),
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test("price alert: create from the trade rail, list, delete", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "alert rail is a desktop panel");
    await page.goto("/trade/XAUUSD");
    const panel = page.getByTestId("price-alerts");
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await page.getByTestId("price-alert-level").fill("4321.5");
    await page.getByTestId("price-alert-create").click();
    await expect(panel.getByText("4,321.50")).toBeVisible({ timeout: 5_000 });
    // notify-only invariant: creating an alert must not touch the book
    const status = await page.request.get("/api/status",
      { headers: { "X-API-Key": TOKEN } });
    expect((await status.json()).trading_halted).not.toBe(true);
    await panel.getByRole("button", { name: /Delete alert/ }).click();
    await expect(panel.getByText("4,321.50")).toBeHidden({ timeout: 5_000 });
  });

  test("parameterized indicator id resolves server-side", async ({ page }) => {
    const series = await page.request.get(
      "/api/bars/indicators?symbol=XAUUSD&timeframe=1d&names=EMA_21",
      { headers: { "X-API-Key": TOKEN } });
    expect(series.status()).toBe(200);
    expect((await series.json()).EMA_21.params.period).toBe(21);
    const bad = await page.request.get(
      "/api/bars/indicators?symbol=XAUUSD&timeframe=1d&names=EMA_9999",
      { headers: { "X-API-Key": TOKEN } });
    expect(bad.status()).toBe(422);
  });

  test("intel calendar defaults to majors with countdown", async ({ page }) => {
    await page.goto("/intel");
    const toggle = page.getByTestId("calendar-majors-toggle");
    await expect(toggle).toBeVisible({ timeout: 10_000 });
    await expect(toggle).toHaveText(/major only/);
  });

  test("paper mode shows no live banner or flatten control", async ({
    page,
  }) => {
    // safety-critical direction: the live-armed banner and its one
    // execution write must NEVER appear while every pair is paper (the
    // demo server's default state).
    await unlock(page);
    await expect(page.getByTestId("risk-badge")).toBeVisible();
    await expect(page.getByTestId("arming-banner")).toHaveCount(0);
    await expect(page.getByTestId("emergency-flatten")).toHaveCount(0);
  });
});

test.describe("v-golive Phase 5 ops", () => {
  test("health endpoint is reachable and unauthenticated", async ({
    request,
  }) => {
    // /health/live is auth-exempt like /healthz; 200 or 503 (a JSON
    // verdict) both count as reachable — never a 401.
    const resp = await request.get("/health/live");
    expect([200, 503]).toContain(resp.status());
    const body = await resp.json();
    expect(body).toHaveProperty("ok");
    expect(body).toHaveProperty("checks");
  });
});
