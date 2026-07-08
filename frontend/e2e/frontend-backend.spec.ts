import { expect, test } from '@playwright/test';

test('frontend can register, create a monitor, and read generated config from backend', async ({ page }) => {
  const unique = Date.now();
  const email = `operator-${unique}@example.com`;
  const password = 'password123';
  const monitorName = `E2E API ${unique}`;
  const monitorSlug = monitorName.toLowerCase().replace(/[^a-z0-9_.:-]+/g, '-');

  await page.goto('/register');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByLabel('Confirm password').fill(password);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect(page.getByRole('heading', { name: 'Fleet status at a glance' })).toBeVisible();
  await expect(page.getByText('Create your first monitor or upload a config to get started.')).toBeVisible();

  await page.getByRole('button', { name: 'New monitor' }).click();
  await expect(page.getByRole('heading', { name: 'Build from UI, keep config-ready' })).toBeVisible();

  await page.getByLabel('Monitor name').fill(monitorName);
  await page.getByLabel('Target URL').fill('https://example.com/health');
  await page.getByLabel('Interval (seconds)').fill('120');
  await page.getByLabel('Expected status').fill('200');
  await page.getByLabel('Body contains').fill('ok');
  await page.getByRole('button', { name: 'Save HTTP monitor' }).click();

  await expect(page.getByRole('heading', { name: 'Fleet status at a glance' })).toBeVisible();
  await expect(page.getByRole('heading', { name: monitorName })).toBeVisible();
  await expect(page.getByText('https://example.com/health')).toBeVisible();

  await page.getByRole('button', { name: 'Open config' }).click();
  await expect(page.getByRole('heading', { name: 'Edit the source of truth' })).toBeVisible();
  await expect(page.locator('textarea')).toContainText(`id: ${monitorSlug}`);
  await expect(page.locator('textarea')).toContainText('url: https://example.com/health');
});
