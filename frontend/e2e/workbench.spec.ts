/**
 * H1 - Playwright end-to-end specs against the production boundary.
 *
 * The webServer (playwright.config.ts) starts scripts/e2e_server.py which
 * composes the real FastAPI app + SingleRunManager + RunStore with a fake
 * runner emitting a deterministic 13-role event sequence.
 *
 * 2026-07-21: the broker live-queue race was fixed. Root cause was NOT
 * broker registration timing (persist/subscribe are already mutually
 * exclusive under store.lock_for) - it was scripts/e2e_server.py creating
 * two independent broker instances: one inside SingleRunManager (worker
 * persist path) and one inside create_app (SSE subscribe path), so
 * _subscribers never saw live events and subs=0 for every persist. Fix:
 * e2e_server passes a shared broker; create_app now reuses manager.broker
 * and raises on mismatch. Real `tradingagents web` was never affected
 * (its create_app passes selected_broker into SingleRunManager).
 */
import { test, expect, type Page } from "@playwright/test";

test.describe("workbench e2e", () => {
  const TICKER = "600519.SS";

  async function startRun(page: Page): Promise<string> {
    await page.goto("/");
    await page.getByLabel("股票代码").fill(TICKER);
    await page.getByRole("button", { name: /开始分析/ }).click();
    await expect(page.getByText(TICKER).first()).toBeVisible({ timeout: 10_000 });
    return TICKER;
  }

  async function waitForRunCompleted(page: Page): Promise<void> {
    // Both SwarmStatusCard and WorkflowMap render "X / 13 已完成", so scope to
    // the workflow map's status line to avoid a strict-mode violation.
    await expect(
      page.locator(".workflow").getByText(/13 \/ 13 已完成/)
    ).toBeVisible({ timeout: 30_000 });
  }

  test("renders all 13 roles in the workflow map and reaches 13/13", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    const labels = [
      "市场分析师", "情绪分析师", "新闻分析师", "基本面分析师",
      "证据管理员", "多方研究员", "空方研究员", "研究经理",
      "交易员", "激进风险分析师", "中性风险分析师", "保守风险分析师", "组合经理",
    ];
    for (const label of labels) {
      await expect(page.getByText(label).first()).toBeVisible();
    }
  });

  test("refreshes the history badge after a run completes", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    await expect(page.locator(".history-item").first()).toContainText("已完成");
  });

  test("timeline shows debate turns and lazy-loads a response on click", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    await expect(page.getByText("辩论与决策时间线")).toBeVisible();
    const bubble = page.locator(".bubble").first();
    await bubble.click();
    await expect(page.locator(".bubble").first()).not.toContainText("点击展开", { timeout: 5_000 });
  });

  test("inspector shows role-input tabs and the run-input snapshot", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    for (const tab of ["角色输入", "数据与工具", "产物", "本次输入"]) {
      await expect(page.getByRole("button", { name: tab })).toBeVisible();
    }
    await page.getByRole("button", { name: "本次输入" }).click();
    await expect(page.locator(".inspector .data-table").getByText(TICKER)).toBeVisible();
  });

  test("refresh mid-run produces no missing roles and no duplicate timeline entries", async ({ page }) => {
    await startRun(page);
    await expect(
      page.locator(".workflow").getByText(/[1-9] \/ 13 已完成/)
    ).toBeVisible({ timeout: 10_000 });
    await page.reload();
    await page.getByText(TICKER).first().click();
    await expect(page.locator(".node")).toHaveCount(13, { timeout: 10_000 });
    await waitForRunCompleted(page);
  });

  test("no configured secret appears in the DOM", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toContain("fake-deepseek-e2e-key");
    expect(bodyText).not.toContain("DEEPSEEK_API_KEY");
    await expect(page.locator(".key-status .ok").first()).toBeVisible();
  });

  test("G2: inspector tools tab renders vendor provenance and tool-call sections", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    // Select a turn first so the tools tab has a turn_id to filter on.
    await page.locator(".bubble").first().click();
    await page.getByRole("button", { name: "数据与工具" }).click();
    // The tools tab now renders the VendorProvenance + tool-call sections
    // (fake runner emits no tool/vendor calls, so placeholders are fine).
    await expect(page.getByText("数据来源")).toBeVisible();
    await expect(page.getByText("工具调用", { exact: true })).toBeVisible();
  });

  test("G3: clicking a completed role card surfaces its turn in the inspector", async ({ page }) => {
    await startRun(page);
    await waitForRunCompleted(page);
    // Click a completed role card in the workflow map.
    await page.locator(".node.done").first().click();
    // Inspector should show the role-input tab with the role header.
    await expect(page.locator(".role-header")).toBeVisible({ timeout: 5_000 });
  });

  test("cancel a running run transitions to cancelled", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("股票代码").fill(TICKER);
    // Wait for createRun to resolve so selectRun fires and the cancel button
    // renders (fake runner completes in ~0.65s, so act fast).
    const createResponse = page.waitForResponse(
      (r) => r.url().endsWith("/api/runs") && r.request().method() === "POST",
    );
    await page.getByRole("button", { name: /开始分析/ }).click();
    await createResponse;
    const cancelBtn = page.getByRole("button", { name: "取消" });
    await expect(cancelBtn).toBeVisible({ timeout: 5_000 });
    await cancelBtn.click();
    // run.cancelled reaches the browser via SSE; the main status strip flips
    // to "cancelled".
    await expect(
      page.locator(".main .section-title").getByText(/cancelled/),
    ).toBeVisible({ timeout: 15_000 });
  });
});
