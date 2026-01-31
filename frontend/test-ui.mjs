import puppeteer from 'puppeteer';
import { writeFile } from 'fs/promises';
import { join } from 'path';

const SESSION_ID = 'session-20260131-152418';
const SCREENSHOT_DIR = `/home/hemang/Documents/GitHub/TradingAgents/.frontend-dev/screenshots/${SESSION_ID}`;
const BASE_URL = 'http://localhost:5173';

const wait = (ms) => new Promise(resolve => setTimeout(resolve, ms));

// Session state
const sessionState = {
  id: SESSION_ID,
  startTime: new Date().toISOString(),
  steps: [],
  currentStep: 0,
  issues: [],
  consoleErrors: [],
};

let browser;
let page;

// Helper to take screenshot
async function takeScreenshot(name, description) {
  sessionState.currentStep++;
  const stepNum = String(sessionState.currentStep).padStart(3, '0');
  const screenshotPath = join(SCREENSHOT_DIR, `step-${stepNum}-${name}.png`);
  
  await page.screenshot({ 
    path: screenshotPath,
    fullPage: false 
  });
  
  sessionState.steps.push({
    stepNumber: sessionState.currentStep,
    name,
    description,
    screenshotPath,
    timestamp: new Date().toISOString()
  });
  
  console.log(`Step ${stepNum}: ${description}`);
  return screenshotPath;
}

async function runTests() {
  try {
    // Launch browser
    console.log('Launching browser...');
    browser = await puppeteer.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });
    page = await browser.newPage();
    
    // Listen to console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        sessionState.consoleErrors.push({
          text: msg.text(),
          timestamp: new Date().toISOString()
        });
      }
    });
    
    // Set viewport to desktop
    await page.setViewport({ width: 1920, height: 1080 });
    
    console.log('Starting iterative testing...\n');
    
    // ===== SCENARIO 1: Dashboard Testing =====
    console.log('=== SCENARIO 1: Dashboard Testing ===');
    
    // Step 1: Navigate to Dashboard
    await page.goto(BASE_URL, { waitUntil: 'networkidle0' });
    await takeScreenshot('dashboard-initial', 'Initial dashboard load');
    
    // Step 2: Test Buy filter
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const buyButton = buttons.find(btn => btn.textContent.includes('Buy ('));
      if (buyButton) buyButton.click();
    });
    await wait(500);
    await takeScreenshot('dashboard-buy-filter', 'After clicking Buy filter');
    
    // Step 3: Test Hold filter
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const holdButton = buttons.find(btn => btn.textContent.includes('Hold ('));
      if (holdButton) holdButton.click();
    });
    await wait(500);
    await takeScreenshot('dashboard-hold-filter', 'After clicking Hold filter');
    
    // Step 4: Test Sell filter
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const sellButton = buttons.find(btn => btn.textContent.includes('Sell ('));
      if (sellButton) sellButton.click();
    });
    await wait(500);
    await takeScreenshot('dashboard-sell-filter', 'After clicking Sell filter');
    
    // Step 5: Back to All filter
    await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const allButton = buttons.find(btn => btn.textContent.includes('All ('));
      if (allButton) allButton.click();
    });
    await wait(500);
    await takeScreenshot('dashboard-all-filter', 'Back to All filter');
    
    // ===== SCENARIO 2: Stock Detail =====
    console.log('\n=== SCENARIO 2: Stock Detail ===');
    
    // Click on first stock
    const firstStock = await page.$('a[href*="/stock/"]');
    if (firstStock) {
      await firstStock.click();
      await wait(1000);
      await takeScreenshot('stock-detail', 'Stock detail page loaded');
    }
    
    // ===== SCENARIO 3: History Page =====
    console.log('\n=== SCENARIO 3: History Page ===');
    
    await page.goto(`${BASE_URL}/history`, { waitUntil: 'networkidle0' });
    await takeScreenshot('history-initial', 'History page loaded');
    
    // Select a date
    const dateButton = await page.$('button[class*="px-3 py-1.5"]');
    if (dateButton) {
      await dateButton.click();
      await wait(500);
      await takeScreenshot('history-date-selected', 'After selecting a date');
    }
    
    // ===== SCENARIO 4: All Stocks Page =====
    console.log('\n=== SCENARIO 4: All Stocks Page ===');
    
    await page.goto(`${BASE_URL}/stocks`, { waitUntil: 'networkidle0' });
    await takeScreenshot('stocks-initial', 'All stocks page loaded');
    
    // Test search
    await page.type('input[type="text"]', 'RELIANCE');
    await wait(500);
    await takeScreenshot('stocks-search', 'After searching for RELIANCE');
    
    // Clear and test another search
    await page.evaluate(() => {
      const input = document.querySelector('input[type="text"]');
      if (input) input.value = '';
    });
    await page.type('input[type="text"]', 'HDFC');
    await wait(500);
    await takeScreenshot('stocks-search-hdfc', 'After searching for HDFC');
    
    // ===== SCENARIO 5: Mobile Testing =====
    console.log('\n=== SCENARIO 5: Mobile Testing ===');
    
    await page.setViewport({ width: 375, height: 667 });
    await page.goto(BASE_URL, { waitUntil: 'networkidle0' });
    await takeScreenshot('mobile-dashboard', 'Mobile dashboard view');
    
    // Test mobile menu
    const menuButton = await page.$('button[class*="md:hidden"]');
    if (menuButton) {
      await menuButton.click();
      await wait(500);
      await takeScreenshot('mobile-menu-open', 'Mobile hamburger menu opened');
      
      // Close menu
      await menuButton.click();
      await wait(500);
      await takeScreenshot('mobile-menu-closed', 'Mobile hamburger menu closed');
    }
    
    // Mobile history page
    await page.goto(`${BASE_URL}/history`, { waitUntil: 'networkidle0' });
    await takeScreenshot('mobile-history', 'Mobile history page');
    
    // Mobile stocks page
    await page.goto(`${BASE_URL}/stocks`, { waitUntil: 'networkidle0' });
    await takeScreenshot('mobile-stocks', 'Mobile stocks page');
    
    // ===== HOVER STATES TESTING =====
    console.log('\n=== Testing Hover States (Desktop) ===');
    
    await page.setViewport({ width: 1920, height: 1080 });
    await page.goto(BASE_URL, { waitUntil: 'networkidle0' });
    
    // Hover over stock card
    const stockCard = await page.$('a[href*="/stock/"]');
    if (stockCard) {
      await stockCard.hover();
      await wait(300);
      await takeScreenshot('hover-stock-card', 'Hovering over stock card');
    }
    
    // Hover over navigation
    const navLink = await page.$('a[href="/history"]');
    if (navLink) {
      await navLink.hover();
      await wait(300);
      await takeScreenshot('hover-nav-link', 'Hovering over navigation link');
    }
    
    // ===== FINAL STATE =====
    sessionState.endTime = new Date().toISOString();
    sessionState.testingComplete = true;
    
    // Save session state
    const sessionPath = `/home/hemang/Documents/GitHub/TradingAgents/.frontend-dev/sessions/${SESSION_ID}.json`;
    await writeFile(sessionPath, JSON.stringify(sessionState, null, 2));
    
    console.log(`\n=== Testing Complete ===`);
    console.log(`Steps completed: ${sessionState.currentStep}`);
    console.log(`Console errors: ${sessionState.consoleErrors.length}`);
    console.log(`Issues found: ${sessionState.issues.length}`);
    console.log(`Session saved to: ${sessionPath}`);
    
  } catch (error) {
    console.error('Test error:', error);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

runTests();
