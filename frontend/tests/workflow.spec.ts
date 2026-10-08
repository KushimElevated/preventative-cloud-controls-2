import { test, expect, type Page } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  page.on('pageerror', error => console.error('BROWSER_ERROR', error.stack || error.message));
});

async function switchIdentity(page: Page, identity: string) {
  const picker = page.getByLabel('Switch demo identity');
  await picker.selectOption(identity);
  await expect(picker).toHaveValue(identity);
  await expect(picker).toBeEnabled();
}

test('Azure intent → assessment → distinct approvals → export → mock verified coverage', async ({ page }) => {
  await page.goto('/dashboard');
  await page.getByRole('button', { name: 'Enter workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Build prevention. Prove coverage.' })).toBeVisible();
  await switchIdentity(page, 'admin');
  await page.getByRole('link', { name: 'Demo workspace' }).click();
  await page.getByRole('button', { name: 'Load remediated fixture' }).click();
  await expect(page.getByRole('status')).toContainText('New synthetic snapshot');
  await switchIdentity(page, 'engineer');
  await page.goto('/controls/azure-search/simulation');
  await page.getByRole('button', { name: 'Run assessment' }).click();
  await expect(page.getByText('Ready for package review.')).toBeVisible();
  await page.getByRole('button', { name: 'Prepare rollout' }).click();
  await page.getByLabel('Cloud Engineering rollback and recovery runbook').fill('Cloud Engineering reviews and restores the previous known-good policy assignment, then verifies application connectivity.');
  await page.getByRole('button', { name: 'Create package' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('link', { name: 'Rollouts & handoff' }).click();
  await expect(page.getByRole('heading', { name: 'Progressive rollout & handoff' })).toBeVisible();
  for (const who of ['security', 'cloud']) {
    await switchIdentity(page, who);
    await page.getByLabel(/Review rationale /).first().fill('Reviewed the precise demo manifest, prerequisites and rollback.');
    await page.getByRole('button', { name: 'Approve package' }).first().click();
    await expect(page.getByRole('status')).toContainText('Review recorded');
  }
  await switchIdentity(page, 'engineer');
  await page.getByRole('button', { name: 'Advance to observation' }).first().click();
  await page.getByRole('button', { name: 'Advance to pilot' }).first().click();
  const downloaded = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Approved handoff', exact: true }).first().click();
  expect((await downloaded).suggestedFilename()).toContain('approved-demo');
  await switchIdentity(page, 'cloud');
  await page.getByRole('button', { name: 'Record mock verified' }).first().click();
  await expect(page.getByRole('status')).toContainText('Mock verified receipt');
  await page.getByRole('link', { name: 'Overview', exact: true }).click();
  await expect(page.getByText('6 of 10 applicable control-resource pairs')).toBeVisible();
  await page.screenshot({ path: 'test-results/dashboard.png', fullPage: true });
});

test('catalog search and scope-restricted identity', async ({ page }) => {
  await page.goto('/controls');
  await page.getByRole('button', { name: 'Enter workspace' }).click();
  await page.getByLabel('Search controls').fill('S3');
  await expect(page.getByText('Protect S3 public-access safeguards', { exact: true })).toBeVisible();
  await expect(page.getByText('Prevent public access to Azure AI Search', { exact: true })).toHaveCount(0);
  await switchIdentity(page, 'dev-requester');
  await expect(page.getByText('No controls in your scope')).toBeVisible();
});
