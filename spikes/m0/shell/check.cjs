// Headless check of the shell spike: deterministic A2UI render + host component + action dispatch.
const { chromium } = require("playwright");
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const base = process.argv[2];
  const results = {};
  for (const who of ["appr", "eng"]) {
    await page.goto(`${base}/index.html?m=${who}.json`);
    await page.waitForFunction(() => window.__ready === true, null, { timeout: 15000 });
    await page.waitForTimeout(500);
    const text = await page.locator("#root").innerText();
    const buttons = await page.locator("#root button").allInnerTexts();
    const badge = await page.locator('[data-testid="acme-badge"]').allInnerTexts();
    results[who] = { buttons, badge, hasDesign: text.includes("Design"), hasHeading: text.includes("Experiment E1") };
    if (who === "appr" && buttons.length) {
      await page.locator("#root button").first().click();
      await page.waitForTimeout(300);
      results.appr.actions = await page.evaluate(() => window.__actions);
      await page.screenshot({ path: "spike-shell.png", fullPage: true });
    }
  }
  console.log(JSON.stringify({ results, errors }, null, 1));
  await browser.close();
})();
