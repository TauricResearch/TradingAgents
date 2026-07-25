import { expect, test } from '@playwright/test'

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1024, height: 768 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'narrow-mobile', width: 360, height: 800 },
]

function jobStatus(page: import('@playwright/test').Page) {
  return page.locator('.summary-band > div').nth(3).locator('strong')
}

for (const viewport of viewports) {
  test(`${viewport.name}: configure, stream, complete without overflow`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const consoleErrors: string[] = []
    page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
    await page.goto('/')
    if (viewport.width < 760) await page.getByLabel('Open configuration').click()
    await page.screenshot({ path: `test-results/${viewport.name}-configuration.png`, fullPage: true })
    await page.getByRole('button', { name: 'Resolve' }).click()
    await expect(page.locator('.identity-block').getByText('SPDR S&P 500 ETF Trust')).toBeVisible()
    await page.getByRole('button', { name: /Start analysis/ }).click()
    await expect(jobStatus(page)).toHaveText('running')
    await page.screenshot({ path: `test-results/${viewport.name}-running.png`, fullPage: true })
    await expect(jobStatus(page)).toHaveText('completed', { timeout: 12_000 })
    await expect(page.getByText('Adjusted price vs benchmark')).toBeVisible()
    await page.screenshot({ path: `test-results/${viewport.name}-completed.png`, fullPage: true })
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
    expect(overflow).toBe(false)
    expect(consoleErrors).toEqual([])
  })
}

test('cancel leaves controls usable and stock hides fund panels', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Symbol').fill('SLOW')
  await page.getByRole('button', { name: 'Resolve' }).click()
  await page.getByRole('button', { name: /Start analysis/ }).click()
  await page.getByRole('button', { name: /Cancel analysis/ }).click()
  await expect(jobStatus(page)).toHaveText('cancelled')
  await expect(page.getByRole('button', { name: /Start analysis/ })).toBeEnabled()

  await page.getByRole('button', { name: 'stock' }).click()
  await page.getByLabel('Symbol').fill('AAPL')
  await page.getByRole('button', { name: 'Resolve' }).click()
  await expect(page.locator('.identity-block').getByText('Apple Inc.')).toBeVisible()
  await expect(page.getByText('Top holdings')).toHaveCount(0)
})

test('mobile renders explicit missing holdings state', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await page.getByLabel('Open configuration').click()
  await page.getByLabel('Symbol').fill('EMPTY')
  await page.getByRole('button', { name: 'Resolve' }).click()
  await page.getByRole('button', { name: /Start analysis/ }).click()
  await expect(jobStatus(page)).toHaveText('completed')
  await expect(page.getByText('Holdings unavailable from the provider.')).toBeVisible()
  await page.screenshot({ path: 'test-results/mobile-missing-data.png', fullPage: true })
})

test('desktop renders safe provider failure and preserves form', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByLabel('Symbol').fill('FAIL')
  await page.getByRole('button', { name: 'Resolve' }).click()
  await page.getByRole('button', { name: /Start analysis/ }).click()
  await expect(page.getByText('Provider is temporarily unavailable')).toBeVisible()
  await expect(page.getByLabel('Symbol')).toHaveValue('FAIL')
  await page.screenshot({ path: 'test-results/desktop-failure.png', fullPage: true })
})

test('desktop shows Yahoo rate-limit state, zero CIII usage, and explicit retry', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByLabel('Symbol').fill('RATE')
  await page.getByRole('button', { name: /Start analysis/ }).click()
  await expect(jobStatus(page)).toHaveText('provider rate limited')
  await expect(page.getByText('Yahoo Finance rate limited')).toBeVisible()
  await expect(page.getByText(/CIII usage: 0 requests, 0 tokens, 0 retries/)).toBeVisible()
  await page.getByRole('button', { name: 'Retry later' }).click()
  await expect(jobStatus(page)).toHaveText('completed', { timeout: 12_000 })
  await page.screenshot({ path: 'test-results/desktop-provider-rate-limit-retry.png', fullPage: true })
})

test('desktop shows Yahoo timeout and waits for the user to retry', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.getByLabel('Symbol').fill('TIME')
  await page.getByRole('button', { name: /Start analysis/ }).click()
  await expect(jobStatus(page)).toHaveText('provider timed out')
  await expect(page.getByText('Yahoo Finance timed out')).toBeVisible()
  await expect(page.getByText(/Request timeout: 10s. CIII usage: 0 requests, 0 tokens, 0 retries/)).toBeVisible()
  await page.screenshot({ path: 'test-results/desktop-provider-timeout.png', fullPage: true })
  await page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(jobStatus(page)).toHaveText('completed', { timeout: 12_000 })
  await page.screenshot({ path: 'test-results/desktop-provider-timeout-retry.png', fullPage: true })
})

test('desktop persists trust, usage, chat, advice versions, history, and backup', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 })
  await page.goto('/')
  await page.getByRole('button', { name: 'Resolve' }).click()
  await page.getByRole('button', { name: /Start analysis/ }).click()
  await expect(jobStatus(page)).toHaveText('completed', { timeout: 12_000 })

  await page.getByRole('button', { name: 'Data Quality' }).click()
  await expect(page.getByText('Deterministic trust gate')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'trusted' })).toBeVisible()
  await page.screenshot({ path: 'test-results/desktop-data-quality.png', fullPage: true })

  await page.getByRole('button', { name: 'Usage' }).click()
  await expect(page.getByText('Configured budget')).toBeVisible()
  await expect(page.getByText('Recorded usage')).toBeVisible()

  await page.getByRole('button', { name: 'Advice' }).click()
  await expect(page.getByText('Advice version comparison')).toBeVisible()
  await expect(page.locator('.version-compare article').first().getByText('Version 1')).toBeVisible()

  await page.getByRole('button', { name: 'Q&A' }).click()
  await page.getByRole('button', { name: 'Start conversation' }).click()
  await page.getByLabel('Question').fill('Candidate adjustment: sell if current data conflicts.')
  await page.getByText('Retrieve current data').click()
  await page.getByText('Candidate adjustment', { exact: true }).click()
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.getByText(/Fresh-data marker:/)).toBeVisible()
  await expect(page.getByText('Formal advice is unchanged', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Re-evaluate' }).click()
  await expect(page.getByText(/Formal advice version 2 created/)).toBeVisible()
  await page.screenshot({ path: 'test-results/desktop-persisted-chat.png', fullPage: true })

  await page.reload()
  await page.getByRole('button', { name: 'History' }).click()
  await expect(page.getByText('Analysis history')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open' }).first()).toBeEnabled()

  await page.getByRole('button', { name: 'Backup' }).click()
  await page.getByRole('button', { name: 'Create backup' }).click()
  await expect(page.getByText('Backup created')).toBeVisible()
  await page.locator('.backup-row').first().click()
  await page.getByRole('button', { name: 'Preview restore' }).click()
  await expect(page.getByText('Restore preview complete')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Commit restore' })).toBeEnabled()
})

test('mobile Phase 2 work views remain usable without page overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  for (const tab of ['History', 'Data Quality', 'Usage', 'Advice', 'Q&A', 'Backup']) {
    await page.getByRole('button', { name: tab, exact: true }).click()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
    expect(overflow, `${tab} caused document overflow`).toBe(false)
  }
  await page.screenshot({ path: 'test-results/mobile-phase2-backup.png', fullPage: true })
})

for (const viewport of [{ name: 'desktop', width: 1440, height: 900 }, { name: 'mobile', width: 390, height: 844 }]) {
  test(`${viewport.name}: Chinese interface persists and report language remains independent`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/')
    await page.getByLabel('Interface language').selectOption('zh')
    await expect(page.getByRole('button', { name: '开始分析' })).toBeVisible()
    await expect(page.getByLabel('报告语言')).toHaveValue('English')
    await page.reload()
    await expect(page.getByRole('button', { name: '概览' })).toBeVisible()
    await expect(page.getByLabel('界面语言')).toHaveValue('zh')
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
    expect(overflow).toBe(false)
    await page.screenshot({ path: `test-results/${viewport.name}-chinese-interface.png`, fullPage: true })
  })
}
