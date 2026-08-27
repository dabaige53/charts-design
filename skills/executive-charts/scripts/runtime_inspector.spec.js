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
    const standaloneChart = page.locator('#chart-main');
    if (await standaloneChart.count()) {
      await expect.poll(
        async () => standaloneChart.locator('canvas, svg').count(),
        { message: 'standalone chart creates a rendered canvas or SVG' }
      ).toBeGreaterThan(0);
      const dimensions = await standaloneChart.evaluate(element => ({
        width: element.clientWidth,
        height: element.clientHeight
      }));
      expect(dimensions.width, 'standalone chart width').toBeGreaterThan(0);
      expect(dimensions.height, 'standalone chart height').toBeGreaterThan(0);

      const explainTrigger = page.locator('.chart-explain-btn[data-explain-chart]');
      await expect(explainTrigger, 'standalone explanation trigger exists').toHaveCount(1);
      await expect(explainTrigger, 'explanation trigger has the canonical accessible label').toHaveAttribute('aria-label', '查看业务口径说明');
      const triggerContract = await explainTrigger.evaluate(element => {
        const rect = element.getBoundingClientRect();
        const icon = element.querySelector('svg');
        return {
          width: rect.width,
          height: rect.height,
          iconWidth: icon?.getAttribute('width'),
          iconHeight: icon?.getAttribute('height')
        };
      });
      expect(triggerContract, 'canonical explanation trigger dimensions').toEqual({
        width: 22,
        height: 22,
        iconWidth: '12',
        iconHeight: '12'
      });
      await explainTrigger.click();
      const dialog = page.locator('#app-explain-dialog');
      await expect(dialog, 'shared explanation dialog opens').toHaveAttribute('open', '');
      await expect(page.locator('#explainDialog'), 'legacy explanation dialog is removed').toHaveCount(0);
      await expect(dialog.locator('.exp-overview-box'), 'shared overview card exists').toHaveCount(1);
      await expect(dialog.locator('.exp-axis-grid'), 'shared axis cards exist').toHaveCount(1);
      await expect(dialog.locator('.exp-metric-card'), 'shared metric cards exist').toHaveCount(1);
      const centering = await dialog.evaluate(element => {
        const rect = element.getBoundingClientRect();
        return {
          x: Math.abs(rect.left + rect.width / 2 - window.innerWidth / 2),
          y: Math.abs(rect.top + rect.height / 2 - window.innerHeight / 2)
        };
      });
      expect(centering.x, 'explanation dialog is horizontally centered').toBeLessThanOrEqual(1);
      expect(centering.y, 'explanation dialog is vertically centered').toBeLessThanOrEqual(1);
      await page.keyboard.press('Escape');
      await expect(dialog, 'Escape closes shared explanation dialog').not.toHaveAttribute('open', '');
    }
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

  const explainTrigger = page.locator('[data-explain-chart]').first();
  if (await explainTrigger.count()) {
    await explainTrigger.click();
    const dialog = page.locator('#app-explain-dialog');
    await expect(dialog, 'explanation dialog opens').toHaveAttribute('open', '');
    await expect(dialog.locator('#closeExplainModalBtn'), 'title-bar close control exists').toHaveCount(1);
    await expect(dialog.getByRole('button', { name: '我知道了' }), 'read-only dialog has no confirmation action').toHaveCount(0);
    await expect(dialog.locator('#closeExplainModalFooterBtn'), 'read-only dialog has no action footer').toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(dialog, 'Escape closes explanation dialog').not.toHaveAttribute('open', '');
  }

  const lifecycle = await page.evaluate(() => {
    const firstApp = window.App;
    const root = window.DashboardRuntime.root;
    window.DashboardRuntime.destroy();
    const destroyed = !window.App && !window.DashboardRuntime.app && window.DashboardRuntime.root === root;
    const remountedApp = window.DashboardRuntime.mount();
    const remounted = remountedApp !== firstApp
      && remountedApp._mounted
      && remountedApp.root === root
      && window.App === remountedApp;
    window.DashboardRuntime.destroy();
    return { destroyed, remounted, finallyDestroyed: !window.App && !window.DashboardRuntime.app };
  });
  expect(lifecycle.destroyed, 'runtime destroy clears the mounted app and preserves its root').toBe(true);
  expect(lifecycle.remounted, 'runtime remount creates a fresh app on the preserved root').toBe(true);
  expect(lifecycle.finallyDestroyed, 'runtime can destroy the remounted app').toBe(true);
});

test('two container roots keep real filter controls and lifecycle isolated', async ({ page }) => {
  const htmlPath = process.env.EXECUTIVE_CHARTS_HTML;
  expect(htmlPath, 'EXECUTIVE_CHARTS_HTML is required').toBeTruthy();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'domcontentloaded' });
  const hasDashboardRuntime = await page.evaluate(() => Boolean(window.createDashboardRuntime));
  if (!hasDashboardRuntime) return;

  const setup = await page.evaluate(() => {
    window.DashboardRuntime?.destroy();
    const shell = () => `
      <header id="app-header"></header>
      <section id="app-filters"></section>
      <main>
        <section id="app-kpis"></section>
        <section id="app-charts-grid"></section>
        <section id="app-table-section"></section>
      </main>
      <dialog id="app-explain-dialog"></dialog>
      <div id="app-toast-container"></div>`;
    const config = {
      meta: { title: 'Scoped runtime' },
      filters: [{
        id: 'region', key: 'region', label: 'Region', type: 'select',
        fields: ['region'], componentIds: [],
        options: [
          { value: 'east', label: 'East', default: true },
          { value: 'south', label: 'South' }
        ]
      }],
      kpis: [], charts: [],
      table: {
        id: 'detail', title: 'Detail',
        columns: [{ key: 'region', title: 'Region', align: 'left' }],
        rows: [{ region: 'east' }, { region: 'south' }]
      }
    };
    document.body.innerHTML = '<div id="left-root"></div><div id="right-root"></div>';
    const left = document.getElementById('left-root');
    const right = document.getElementById('right-root');
    left.innerHTML = shell();
    right.innerHTML = shell();
    window.leftRuntime = window.createDashboardRuntime(config, left);
    window.rightRuntime = window.createDashboardRuntime(config, right);
    window.leftRuntime.mount();
    window.rightRuntime.mount();
    return { leftMounted: window.leftRuntime.app._mounted, rightMounted: window.rightRuntime.app._mounted };
  });
  expect(setup).toEqual({ leftMounted: true, rightMounted: true });

  const left = page.locator('#left-root');
  const right = page.locator('#right-root');
  await left.getByRole('button', { name: /Region:/ }).click();
  await left.locator('#filterMenu_region').getByText('South', { exact: true }).click();

  const isolation = await page.evaluate(() => {
    const leftBeforeDestroy = window.leftRuntime.app.state.filterValues.region;
    const rightBeforeDestroy = window.rightRuntime.app.state.filterValues.region;
    window.leftRuntime.destroy();
    const rightAfterDestroy = window.rightRuntime.app._mounted
      && document.getElementById('right-root').__dashboardApp === window.rightRuntime.app;
    const remounted = window.leftRuntime.mount();
    return {
      leftBeforeDestroy,
      rightBeforeDestroy,
      rightAfterDestroy,
      leftRemounted: remounted._mounted
        && document.getElementById('left-root').__dashboardApp === remounted
    };
  });

  expect(isolation).toEqual({
    leftBeforeDestroy: 'south',
    rightBeforeDestroy: 'east',
    rightAfterDestroy: true,
    leftRemounted: true
  });
  await expect(right.locator('#selectedLabel_region')).toHaveText('East');
});
