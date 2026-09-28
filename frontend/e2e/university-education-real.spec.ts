import { expect, test } from '@playwright/test';

test('university education sections load on desktop and mobile', async ({ page }) => {
  const universityId = process.env.E2E_UNIVERSITY_ID;
  test.skip(!universityId || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD,
    'Requires a university ID and local admin credentials.');

  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/universities/${universityId}?tab=students`);
    const learners = page.locator('section[aria-label="Обучающиеся"]');
    await expect(learners).toBeVisible();
    await expect(learners.getByText('Потоков')).toBeVisible();
    await expect(learners.getByRole('button', { name: 'Добавить' })).toBeVisible();
    await page.goto(`/universities/${universityId}?tab=teachers`);
    const teachers = page.locator('section[aria-label="Преподаватели"]');
    await expect(teachers).toBeVisible();
    await expect(teachers.getByRole('button', { name: 'Добавить преподавателя' })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
  }
});
