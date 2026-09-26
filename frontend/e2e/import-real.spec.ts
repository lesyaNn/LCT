import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

test('real import wizard: upload, mapping, dry-run, execute, persisted result', async ({ page }) => {
  const username = process.env.E2E_MANAGER_USERNAME?.trim();
  const password = process.env.E2E_MANAGER_PASSWORD?.trim();
  test.skip(!username || !password, 'Set E2E_MANAGER_USERNAME and E2E_MANAGER_PASSWORD for the real import smoke.');

  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await page.goto('/admin/import');

  await page.getByRole('combobox', { name: 'Тип справочника' }).selectOption('universities');
  const previewResponse = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/import/preview');
  await page.locator('input[type="file"]').setInputFiles(resolve(process.cwd(), '../docs/import-example-20.xlsx'));
  expect((await previewResponse).status()).toBe(200);
  await expect(page.getByTestId('mapping-select-0')).toHaveValue('university.name');
  await expect(page.getByTestId('preview-table')).toBeVisible();

  const dryResponse = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/import/execute');
  await page.getByRole('button', { name: 'Запустить dry-run' }).click();
  const dryJob = await (await dryResponse).json() as { job_id: string };
  expect(dryJob.job_id).toBeTruthy();
  await expect(page.getByText('Проверочный запуск завершён')).toBeVisible({ timeout: 120_000 });

  const allowErrors = page.getByLabel('Пропустить строки с ошибками при итоговом импорте');
  if (await allowErrors.isVisible()) await allowErrors.check();

  const realResponse = page.waitForResponse((response) => response.request().method() === 'POST'
    && new URL(response.url()).pathname === '/api/v1/import/execute');
  await page.getByTestId('import-confirm').click();
  const realJob = await (await realResponse).json() as { job_id: string };
  expect(realJob.job_id).toBeTruthy();
  expect(realJob.job_id).not.toBe(dryJob.job_id);
  await expect(page.getByText('Импорт завершён')).toBeVisible({ timeout: 120_000 });

  await page.reload();
  await expect(page.getByTestId('import-job-row').first()).toBeVisible();
  await expect(page.getByText('import-example-20.xlsx').first()).toBeVisible();
});
