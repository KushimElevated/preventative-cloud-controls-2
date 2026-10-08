import { test, expect, type Page } from '@playwright/test';

async function switchIdentity(page: Page, id: string) {
  const picker = page.getByLabel('Switch demo identity');
  await picker.selectOption(id);
  await expect(picker).toHaveValue(id);
  await expect(picker).toBeEnabled();
}

test.beforeEach(async ({ page }) => {
  page.on('pageerror', e => console.error('BROWSER_ERROR', e.stack || e.message));
});

test('A2UI engineering workspace filters evidence, selects scopes and confirms a draft through trusted UI', async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Enter workspace' }).click();
  await page.getByRole('link').filter({ hasText: 'Open engineering assistant' }).click();
  await expect(page.getByRole('heading', { name: 'From question to governed decision.' })).toBeVisible();
  await expect(page.getByRole('table').getByText('search-customer', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Noncompliant 5', exact: true }).click();
  await expect(page.getByRole('table').getByText('search-claims', { exact: true })).toHaveCount(0);
  await page.getByLabel('Filter assessed resources').fill('customer');
  await expect(page.getByText('1 of 8 shown', { exact: false })).toBeVisible();
  await page.getByLabel('Assistant target scope').selectOption('az-search-pilot');
  await expect(page.getByText('2 of 2 shown', { exact: false })).toBeVisible();
  await expect(page.getByRole('table').getByText('search-analytics', { exact: true })).toHaveCount(0);
  await page.getByLabel('Assistant target scope').selectOption('az-prod');
  await expect(page.getByText('8 of 8 shown', { exact: false })).toBeVisible();
  const readiness = page.getByText('Readiness review checklist');
  await expect(readiness).toBeVisible();
  await page.getByRole('checkbox').first().check();
  await expect(page.getByRole('heading', { name: 'Review the gaps before enforcement' })).toBeVisible();
  await page.getByLabel('Exception draft resource').selectOption('search-2');
  await page.getByRole('button', { name: 'Draft exception for review' }).click();
  await expect(page.getByRole('dialog', { name: 'Review the exception request' })).toBeVisible();
  await page.getByLabel('Business and technical justification').fill('Customer search needs a temporary migration window for the private endpoint.');
  await page.getByLabel('Compensating controls').fill('Restricted authenticated client network and monitored access, pending validation.');
  await page.getByLabel('Delegated risk owner').fill('Demo customer application owner');
  await page.getByLabel('I reviewed this request.', { exact: false }).check();
  await page.getByRole('button', { name: 'Confirm and submit request' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByText('Exception requested. Security review', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Evidence changed. Reassess before continuing.' })).toBeVisible();
  await page.getByRole('button', { name: 'Refresh assessment' }).click();
  await expect(page.getByRole('heading', { name: 'Review the gaps before enforcement' })).toBeVisible();
  await page.getByRole('button', { name: 'Prepare governed handoff' }).click();
  await expect(page.getByRole('dialog', { name: 'Prepare a rollout package' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel', exact: true }).click();
  await page.screenshot({ path: 'test-results/a2ui-workspace.png', fullPage: true });
  await switchIdentity(page, 'viewer');
  await expect(page.getByRole('button', { name: 'Draft exception for review' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Prepare governed handoff' })).toBeDisabled();
  await page.getByRole('link', { name: 'Conventional view' }).click();
  await expect(page.getByRole('heading', { name: 'Prevent public access to Azure AI Search' })).toBeVisible();
});
