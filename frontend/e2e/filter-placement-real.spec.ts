import { expect, test } from '@playwright/test';

test('Audit and Overview period controls follow main filters at desktop and mobile widths', async ({ page }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Requires local admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');

  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, label] of [['/audit', 'Фильтры истории изменений'], ['/dashboard', 'Фильтры аналитики']] as const) {
      await page.goto(path);
      let panel = page.getByRole('region', { name: label });
      if (width <= 768) {
        await page.getByRole('button', { name: /^Фильтры/ }).first().click();
        panel = page.getByRole('dialog', { name: 'Фильтры' });
      }
      const period = panel.getByRole('group', { name: 'Период' });
      const main = path === '/audit' ? panel.getByRole('searchbox', { name: 'Поиск по журналу' }) : panel.locator('summary[aria-label="ВУЗ"]');
      await expect(period).toBeVisible();
      await expect(main).toBeVisible();
      const periodBox = await period.boundingBox();
      const mainBox = await main.boundingBox();
      expect(periodBox && mainBox && periodBox.y > mainBox.y).toBeTruthy();
      if (path === '/audit' && width === 1440) {
        await main.fill('Проверка скрытия');
        await panel.getByRole('button', { name: /Скрыть фильтры/ }).click();
        await expect(period).toBeHidden();
        await panel.getByRole('button', { name: /Показать фильтры/ }).click();
        await expect(main).toHaveValue('Проверка скрытия');
      }
    }
  }
});
