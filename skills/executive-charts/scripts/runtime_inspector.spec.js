const { test, expect } = require('playwright/test');
const { pathToFileURL } = require('url');

test.use(process.env.EXECUTIVE_CHARTS_BROWSER_CHANNEL ? { channel: process.env.EXECUTIVE_CHARTS_BROWSER_CHANNEL } : {});

test('generated dashboard mounts, exposes every component, and destroys cleanly', async ({ page }) => {
  const htmlPath = process.env.EXECUTIVE_CHARTS_HTML;
  expect(htmlPath, 'EXECUTIVE_CHARTS_HTML is required').toBeTruthy();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));

  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'domcontentloaded' });
  const hasDashboardRuntime = await page.evaluate(() => Boolean(window.createDashboardRuntime));
  if (!hasDashboardRuntime) {
    expect(pageErrors, 'page errors').toEqual([]);
    return;
  }

  await page.waitForFunction(() => window.App?._mounted === true);
  const contract = await page.evaluate(() => {
    const config = window.App.config;
    const ids = Array.from(document.querySelectorAll('[id]'), element => element.id);
    const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
    const missing = [];
    for (const kpi of config.kpis || []) {
      if (!document.getElementById(kpi.id)) missing.push(`kpi:${kpi.id}`);
    }
    for (const chart of config.charts || []) {
      if (!document.getElementById(chart.id)) missing.push(`chart:${chart.id}`);
      const card = document.querySelector(`[data-component-id="${chart.instanceId}"]`);
      if (!card) missing.push(`card:${chart.instanceId}`);
      for (const action of ['view-toggle-btn', 'export-chart-btn', 'copy-chart-btn', 'fullscreen-btn']) {
        if (!card?.querySelector(`.${action}`)) missing.push(`${action}:${chart.instanceId}`);
      }
    }
    for (const filter of window.App.state.filterDefs || []) {
      if (!document.querySelector(`[data-component-id="${filter.id}"]`)) missing.push(`filter:${filter.id}`);
    }
    if (config.table && !document.querySelector(`[data-component-id="${config.table.id || 'table'}"]`)) {
      missing.push(`table:${config.table.id || 'table'}`);
    }
    return { duplicates: [...new Set(duplicates)], missing };
  });

  expect(contract.duplicates, 'duplicate rendered DOM ids').toEqual([]);
  expect(contract.missing, 'missing rendered component capabilities').toEqual([]);
  expect(pageErrors, 'page errors before destroy').toEqual([]);

  const destroyed = await page.evaluate(() => {
    window.DashboardRuntime.destroy();
    return !window.App && !window.DashboardRuntime.app;
  });
  expect(destroyed, 'runtime destroy clears the mounted app').toBe(true);
});
