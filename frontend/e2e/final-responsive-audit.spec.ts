import { expect, test } from '@playwright/test';

test('real CRM routes remain usable at desktop, tablet and mobile widths', async ({ page }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD
    || !process.env.E2E_UNIVERSITY_ID || !process.env.E2E_WORKFLOW_INSTANCE_ID,
  'Set isolated admin credentials and university, Workflow fixture IDs');

  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const unexpectedApiResponses: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('response', (response) => {
    if (response.url().includes('/api/v1/') && response.status() >= 400) {
      unexpectedApiResponses.push(`${response.status()} ${response.request().method()} ${response.url()}`);
    }
  });

  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/login');
    await expect(page.locator('main')).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth),
      { message: `/login overflows at ${width}px` }).toBeLessThanOrEqual(width + 1);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');

  const paths = [
    '/dashboard', '/universities', `/universities/${process.env.E2E_UNIVERSITY_ID}`,
    '/workflows',
    `/workflows/${process.env.E2E_WORKFLOW_INSTANCE_ID}`, '/reports', '/audit',
    '/admin', '/admin/catalogs', '/admin/import', '/admin/users', '/admin/workflow/templates', '/docs',
  ];
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of paths) {
      await page.goto(path);
      await expect.poll(() => new URL(page.url()).pathname).toBe(path);
      await expect(page.locator('main')).toBeVisible();
      await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth),
        { message: `${path} overflows at ${width}px` }).toBeLessThanOrEqual(width + 1);
    }
  }
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(unexpectedApiResponses).toEqual([]);
});
