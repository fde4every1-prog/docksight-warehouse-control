import { test, expect } from '@playwright/test';

// Read-only tests against the managed preview; no fixture operational database.
const origin = process.env.KPI_TEST_ORIGIN || `https://${process.env.REPLIT_DEV_DOMAIN}`;

for (const role of ['fleet', 'supervisor']) {
  test(`${role} can navigate, inspect and filter monthly KPIs`, async ({ page }) => {
    await page.addInitScript(role => localStorage.setItem('demo-persona', role), role);
    await page.goto(`${origin}/workspace/monthly-kpis`);
    await expect(page.getByRole('heading', { name: 'Metrics Dashboard', exact: true })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Baseline' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'Current' })).toBeVisible();
    await expect(page.getByRole('table')).not.toContainText(/n\s*=/);
    await expect(page.getByRole('table')).toContainText('11.31 h');
    await expect(page.getByRole('table')).toContainText('7.38 h');
    await expect(page.getByRole('table')).toContainText('3.93 hours');
    await expect(page.getByText(/Source-to-date|September source coverage/i)).toHaveCount(0);
    await expect(page.getByText('Demo comparison — illustrative results.', { exact: true })).toBeVisible();
    await expect(page.getByText('Order cycle time', { exact: true })).toBeVisible();
    await expect(page.getByText('Human interventions (proxy)', { exact: true })).toBeVisible();
    const details = page.getByRole('button', { name: 'Metric Details & Calculation' });
    await expect(details).toHaveCount(5);
    for (let index = 0; index < 5; index++) await details.nth(index).click();
    await expect(page.getByRole('table')).not.toContainText(/n\s*=/);
    await expect(page.getByRole('table')).not.toContainText(/0\.42|4\.75/);
    await expect(page.getByText('35 / 712', { exact: false })).toBeVisible();
    const filtered = page.waitForResponse(r => r.url().includes('/api/monthly-kpis?warehouse=DC-01'));
    await page.locator('select').last().selectOption('DC-01');
    const response = await filtered;
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.warehouse).toBe('DC-01');
    expect(body.metrics[0].august.sample_size).toBeLessThan(1351);
    await expect(page.getByText('Order cycle time', { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
}

test('admin cannot access monthly KPIs', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('demo-persona', 'admin'));
  await page.goto(`${origin}/workspace/monthly-kpis`);
  await expect(page.getByRole('heading', { name: 'Access Restricted' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Metrics Dashboard', exact: true })).toHaveCount(0);
});

test('error supports retry and empty response is visible', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('demo-persona', 'supervisor'));
  let fail = true;
  await page.route('**/api/monthly-kpis*', async route => {
    if (fail) {
      await route.fulfill({ status: 503, json: { detail: 'KPI records unavailable' } });
    } else {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({ json: { ...body, metrics: [] } });
    }
  });
  await page.goto(`${origin}/workspace/monthly-kpis`);
  await expect(page.getByText('Error loading KPIs')).toBeVisible();
  fail = false;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByText('No metrics found for the selected facility.')).toBeVisible();
});