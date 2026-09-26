import { expect, test } from '@playwright/test';

test('isolated admin edits a real Workflow template and persists it', async ({ page }) => {
  test.skip(process.env.E2E_FINAL_AUDIT_ISOLATED !== '1', 'Requires the disposable final-audit realm and database.');
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/login');
  await page.locator('input[name="username"]').fill(process.env.E2E_FINAL_ADMIN_USERNAME ?? 'admin');
  await page.locator('input[name="password"]').fill(process.env.E2E_FINAL_ADMIN_PASSWORD ?? 'admin123');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');

  const name = `Final audit template ${Date.now()}`;
  await page.goto('/admin/workflow/templates');
  await page.getByRole('button', { name: 'Новый шаблон' }).click();
  const createDialog = page.getByRole('dialog', { name: 'Новый шаблон Workflow' });
  await createDialog.getByLabel('Название').fill(name);
  await createDialog.getByRole('button', { name: 'Создать' }).click();
  await expect(page).toHaveURL(/\/admin\/workflow\/templates\/[0-9a-f-]+\/edit$/i);
  await expect(page.getByRole('heading', { name })).toBeVisible();

  await page.getByRole('button', { name: 'Добавить этап' }).first().click();
  const stageDialog = page.getByRole('dialog', { name: 'Добавить этап' });
  await stageDialog.getByLabel('Название').fill('Первый этап');
  await stageDialog.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText('Первый этап', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Первый этап', { exact: true })).toBeVisible();

  await page.goto('/admin/workflow/templates');
  const row = page.getByRole('listitem').filter({ hasText: name });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: 'Отключить' }).click();
  await expect(row).toContainText('Отключён');
  await page.reload();
  await expect(page.getByRole('listitem').filter({ hasText: name })).toContainText('Отключён');
  expect(pageErrors).toEqual([]);
});
