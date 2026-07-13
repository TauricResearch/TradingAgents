/** Review capture: every route × theme × viewport → PNGs for the
 * quality audit. Not a test — a camera. */
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const OUT = process.argv[2] ?? "/tmp/review-shots";
const BASE = process.argv[3] ?? "http://127.0.0.1:8600";
mkdirSync(OUT, { recursive: true });

const ROUTES = [
  ["home", "/"],
  ["workspace-gold", "/trade/XAUUSD"],
  ["workspace-btc", "/trade/BTC-USD"],
  ["decisions", "/decisions"],
  ["portfolio", "/portfolio"],
  ["intel", "/intel"],
  ["settings", "/settings"],
  ["report", "/report"],
];

const VIEWPORTS = [
  ["desktop", { width: 1440, height: 900 }],
  ["laptop", { width: 1200, height: 800 }],
  ["narrow", { width: 1000, height: 800 }],
  ["mobile", { width: 390, height: 844 }],
];

const browser = await chromium.launch();
for (const [vpName, viewport] of VIEWPORTS) {
  for (const theme of ["dark", "light"]) {
    const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
    const page = await context.newPage();
    // seed theme before app boot
    await page.addInitScript((t) => {
      localStorage.setItem(
        "pro-ui",
        JSON.stringify({ state: { theme: t, symbol: "XAUUSD", timeframe: "1d",
          // version must match the store's persist version, or migrate()
          // resets theme to light and the dark captures silently render light
          lastSeenAt: Date.now(), indicators: ["EMA_10", "RSI_14"], showVolume: true }, version: 1 }),
      );
    }, theme);
    for (const [name, route] of ROUTES) {
      await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(2500); // data + charts settle (SSE never idles)
      await page.screenshot({
        path: `${OUT}/${vpName}-${theme}-${name}.png`,
        fullPage: name !== "workspace-gold" && name !== "workspace-btc",
      });
    }
    await context.close();
  }
}
await browser.close();
console.log("captured to", OUT);
