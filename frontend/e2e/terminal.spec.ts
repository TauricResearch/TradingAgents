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
    await expect(page.getByText("P&L", { exact: false }).first()).toBeVisible();
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

  test("decision pipeline board renders and inspects stages", async ({
    page,
  }) => {
    await page.goto("/decisions");
    const board = page.getByTestId("decision-pipeline");
    await expect(board).toBeVisible();
    // default selection is the judge with its real verdict
    await expect(page.getByTestId("pipeline-detail")).toContainText("Judge — Aldous");
    // clicking a station swaps the detail bar to that stage's output
    await page.getByTestId("pipeline-station-risk_gate").click();
    await expect(page.getByTestId("pipeline-detail")).toContainText("Risk gate — Imara");
    await expect(page.getByTestId("pipeline-replay")).toBeEnabled();
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

  test("chart symbol dropdown switches between BTC and gold", async ({
    page,
  }) => {
    await page.goto("/trade");
    await expect(page.getByTestId("symbol-select")).toHaveValue("BTC-USD");
    await page.getByTestId("symbol-select").selectOption("XAUUSD");
    await expect(page).toHaveURL(/\/trade\/XAUUSD/);
    await expect(page.getByTestId("price-chart").locator("canvas").first()).toBeVisible({
      timeout: 20_000,
    });
    await page.getByTestId("symbol-select").selectOption("BTC-USD");
    await expect(page).toHaveURL(/\/trade\/BTC-USD/);
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

test.describe("gaps v8", () => {
  test.beforeEach(async ({ page }) => unlock(page));

  test("decision board + per-symbol ticket survive symbol mismatch", async ({
    page,
  }) => {
    // Home: board with a hero and the second symbol's compact slot (G1)
    await expect(page.getByTestId("decision-board")).toBeVisible();
    // the ticket UI lives on /decisions now (Trade is chart-only); it
    // shows the demo symbol's decision, and the per-symbol endpoint answers
    // for the OTHER symbol without lying
    await page.goto("/decisions");
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
      // open positions live on Portfolio now (Trade is chart-only)
      await page.goto("/portfolio");
      await expect(
        page.getByTestId("position-unrealized").first(),
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test("price alert: create from the portfolio panel, list, delete", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "alert panel is a desktop panel");
    // price alerts + position plan relocated to Portfolio when Trade
    // became chart-only
    await page.goto("/portfolio");
    const panel = page.getByTestId("price-alerts");
    await expect(panel).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId("position-plan")).toBeVisible();
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
    await page.getByText("RSI", { exact: true }).click();
    await page.keyboard.press("Escape");
    await expect
      .poll(
        async () =>
          page.getByTestId("price-chart").locator("table canvas").count(),
        { timeout: 15_000 },
      )
      .toBeGreaterThan(before);
  });

  test("multi-chart grid adds and removes synced cells", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "the chart grid is a desktop layout");
    await page.goto("/trade/XAUUSD");
    await expect(
      page.getByTestId("price-chart").locator("canvas").first(),
    ).toBeVisible({ timeout: 20_000 });
    const gridSwitch = page.getByTestId("grid-switch");
    const grid = page.getByTestId("chart-grid");

    // 2×2 = main chart + 3 extra crosshair-synced cells stacked below
    await gridSwitch.getByRole("button", { name: "2×2" }).click();
    await expect(grid).toBeVisible({ timeout: 10_000 });
    await expect(grid.getByTestId("price-chart")).toHaveCount(3);
    // each cell is a real chart with its own symbol + timeframe selectors
    await expect(
      grid.locator("canvas").first(),
    ).toBeVisible();

    // 2×1 = main + 1 extra cell
    await gridSwitch.getByRole("button", { name: "2×1" }).click();
    await expect(grid.getByTestId("price-chart")).toHaveCount(1);

    // back to 1 = grid gone
    await gridSwitch.getByRole("button", { name: "1", exact: true }).click();
    await expect(grid).toHaveCount(0);
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
    // points sit in the top half: the volume pane (default-on) owns the
    // bottom of the chart and drawing clicks there are ignored by design
    await placeTwoPoints(page, /Trendline/, [[0.3, 0.15], [0.6, 0.35]]);
    await expect(chart).toHaveAttribute("data-drawings", "1");

    await page.reload();
    await expect(
      page.getByTestId("price-chart"),
    ).toHaveAttribute("data-drawings", "1", { timeout: 20_000 });

    await page.getByRole("button", { name: /Erase/ }).click();
    const box2 = (await page.getByTestId("price-chart").boundingBox())!;
    // scan a short vertical line through the segment midpoint — autoscale
    // can shift the re-projected segment a few px between sessions
    await expect(async () => {
      if ((await chart.getAttribute("data-drawings")) !== "0") {
        for (const dy of [0, -0.03, 0.03, -0.06, 0.06]) {
          await page.mouse.click(
            box2.x + box2.width * 0.45,
            box2.y + box2.height * (0.25 + dy),
          );
        }
      }
      expect(await chart.getAttribute("data-drawings")).toBe("0");
    }).toPass({ timeout: 15_000 });
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
    await page.mouse.click(box.x + box.width * 0.3, box.y + box.height * 0.2);
    await page.keyboard.press("Escape");
    await expect(chart).toHaveAttribute("data-drawings", "0");

    // place a full fib (top half: the volume pane owns the bottom)
    await placeTwoPoints(page, /Fib retracement/, [[0.3, 0.15], [0.6, 0.35]]);
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

    // the Run button lives on the pipeline board header now (the Runs
    // card's duplicate was removed in the horizontal-board parity pass)
    await page.getByTestId("pipeline-run").click();
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

test.describe("chart phase 1: AI annotations", () => {
  // canvas hit-testing races the primitive's paint cycle against synthetic
  // demo data; the feature is verified live. Retry transient canvas-timing
  // flakes rather than block CI on nondeterministic pixel hits.
  test.describe.configure({ retries: 2 });
  test("decision layer renders and click-to-explain opens the popover", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "canvas hit-targets are desktop UX");
    await unlock(page);
    await page.goto("/trade/XAUUSD");
    const chart = page.getByTestId("price-chart");
    await expect(chart.locator("canvas").first()).toBeVisible({
      timeout: 15_000,
    });
    // the demo's recorded run snaps onto the loaded bar window
    await expect(chart).toHaveAttribute("data-annotations", /^[1-9]/, {
      timeout: 15_000,
    });
    // let the annotations primitive paint + register hit-testing
    await page.waitForTimeout(400);

    // click the regime/confidence RIBBON (top ~12px, full-width hit target).
    // The recent demo run sits at the last bar, so its segment is a right-
    // edge band — sweep right→left just inside the price-axis gutter until
    // the popover opens. Each miss leaves the popover closed, so the next
    // click can't accidentally dismiss it.
    // The demo's recorded run sits at (or near) the LAST bar. Its decision
    // marker is the reliable hit target: findNearestRun matches any click
    // within a few px of the entry bar's x, regardless of y (see
    // annotationsPrimitive "entry-bar vicinity"). The entry bar lands just
    // left of the ~68px price-axis gutter, so sweep x offsets around it at
    // a y comfortably inside the price pane. Each miss leaves the popover
    // closed, so the next click can't accidentally dismiss it.
    const box = (await chart.boundingBox())!;
    const popover = page.getByTestId("explain-run-popover");
    let opened = false;
    outer: for (const off of [71, 68, 74, 65, 77, 62, 80, 59, 84] as const) {
      for (const fy of [0.28, 0.42, 0.16] as const) {
        await page.mouse.click(
          box.x + box.width - off,
          box.y + box.height * fy,
        );
        opened = await popover.isVisible().catch(() => false);
        if (opened) break outer;
        await page.waitForTimeout(90);
      }
    }
    await expect(popover).toBeVisible({ timeout: 5_000 });
    // grounded content: verdict + the link to the full decision record
    await expect(popover).toContainText(/Full decision/);
    // Esc closes
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("explain-run-popover")).toHaveCount(0);
  });

  test("replay hides future AI decisions", async ({ page, isMobile }) => {
    test.skip(isMobile, "replay controls are desktop UX");
    await unlock(page);
    await page.goto("/trade/XAUUSD");
    const chart = page.getByTestId("price-chart");
    await expect(chart).toHaveAttribute("data-annotations", /^[1-9]/, {
      timeout: 15_000,
    });
    // start replay: cursor rewinds to 1/4 of history — the run decided
    // at the last bar must disappear from the visible annotation set
    await page.getByRole("button", { name: /Replay/ }).click();
    await expect(page.getByTestId("replay-badge")).toBeVisible();
    await expect(chart).toHaveAttribute("data-annotations", "0");
  });
});

test.describe("chart phase 2: drawing kinds", () => {
  // canvas placement races React's tool-mode commit; retry transient flakes
  test.describe.configure({ retries: 2 });
  test("vertical line places with one click and persists", async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, "drawing toolbar is desktop-only");
    await unlock(page);
    await page.goto("/trade/XAUUSD");
    const chart = page.getByTestId("price-chart");
    await expect(chart.locator("canvas").first()).toBeVisible({
      timeout: 15_000,
    });
    const before = Number(await chart.getAttribute("data-drawings"));
    // vline lives in the clubbed "Lines" group: open its flyout (corner
    // caret) and pick the tool. Afterwards the group's main button reflects
    // the active tool (aria-label + aria-pressed).
    const linesFlyout = page.getByRole("button", { name: "Lines tools" });
    const vlineItem = page.getByRole("menuitem", { name: /Vertical line/ });
    const vlineBtn = page.getByRole("button", { name: /Vertical line/ });
    for (let attempt = 0; attempt < 3; attempt++) {
      await linesFlyout.click();
      await vlineItem.click();
      // wait for the tool to actually arm before clicking the canvas — the
      // click handler reads the mode off a ref that updates on React's next
      // commit, so a same-tick canvas click would run in select mode
      await expect(vlineBtn).toHaveAttribute("aria-pressed", "true");
      const box = (await chart.boundingBox())!;
      // click the chart BODY (mid-height): the top ~10-20% is LWC's
      // autoscale margin (no bar → no time → no placement)
      await page.mouse.click(box.x + box.width * 0.4, box.y + box.height * 0.45);
      await page.waitForTimeout(650);
      if (Number(await chart.getAttribute("data-drawings")) > before) break;
      await page.keyboard.press("Escape");
    }
    expect(Number(await chart.getAttribute("data-drawings"))).toBe(before + 1);
    // legend readout renders OHLC values (phase 2)
    await expect(page.getByTestId("chart-legend")).toContainText(/O \d/);
  });
});

test.describe("backtesting", () => {
  test.beforeEach(async ({ page }) => unlock(page));

  test("configure, view a saved run, and run a live deterministic backtest", async ({
    page,
  }) => {
    await page.goto("/backtest");
    await expect(page.getByTestId("backtest-page")).toBeVisible();
    // controls render
    await expect(page.getByTestId("backtest-asset")).toBeVisible();
    await expect(page.getByTestId("backtest-run")).toBeVisible();

    // the demo seeds one auto-archived run → Saved Runs + a result view
    await expect(page.getByTestId("backtest-saved-runs")).toContainText("XAUUSD");
    await expect(page.getByText(/Saved run —/)).toBeVisible();

    // run a fresh deterministic backtest (synthetic bars in the demo → offline)
    await page.getByTestId("backtest-asset").selectOption("BTC-USD");
    await page.getByTestId("backtest-run").click();
    // progress/live PnL appears, then a completed result panel
    await expect(
      page.getByTestId("backtest-pnl").or(page.getByText(/Result —/)),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/Result — BTC-USD/)).toBeVisible({ timeout: 30_000 });
    // the completed run is auto-archived alongside the seed
    await expect(
      page.getByTestId("backtest-saved-runs").getByText("BTC-USD"),
    ).toBeVisible();
  });
});
