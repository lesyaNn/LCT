import { expect, test } from '@playwright/test';

function requiredEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is required for the read-only E2E smoke test`);
  return value;
}

test('manager can read a university and its current Workflow stage', async ({ page }) => {
  const baseUrl = requiredEnv('E2E_BASE_URL');
  const username = requiredEnv('E2E_MANAGER_USERNAME');
  const password = requiredEnv('E2E_MANAGER_PASSWORD');
  const universityName = requiredEnv('E2E_UNIVERSITY_NAME');
  const workflowId = requiredEnv('E2E_WORKFLOW_INSTANCE_ID');

  let frontendUrl: URL;
  try {
    frontendUrl = new URL(baseUrl);
  } catch {
    throw new Error('E2E_BASE_URL must be an absolute frontend URL');
  }
  if (!['http:', 'https:'].includes(frontendUrl.protocol) || frontendUrl.pathname !== '/') {
    throw new Error('E2E_BASE_URL must be an http(s) frontend origin');
  }
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(workflowId)) {
    throw new Error('E2E_WORKFLOW_INSTANCE_ID must be a UUID');
  }

  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Добро пожаловать' })).toBeVisible();
  await page.getByRole('link', { name: 'Войти через Ростелеком' }).click();
  await page.getByRole('button', { name: 'Войти через Ростелеком' }).click();
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await expect(page).toHaveURL(/\/dashboard(?:[?#]|$)/);

  await page.getByRole('link', { name: 'ВУЗы' }).click();
  await expect(page.getByRole('heading', { name: 'ВУЗы', level: 1 })).toBeVisible();
  await page.getByRole('tab', { name: 'Таблица' }).click();
  await page.getByRole('searchbox', { name: 'Поиск по названию вуза' }).fill(universityName);
  await page.getByRole('link', { name: universityName, exact: true }).click();
  await expect(page.getByRole('heading', { name: universityName, level: 1 })).toBeVisible();

  await page.getByRole('tab', { name: 'Workflow' }).click();
  await expect(page.getByRole('heading', { name: 'Workflow вуза' })).toBeVisible();
  const workflowLink = page.locator(`a[href="/workflows/${workflowId}"]`);
  await expect(workflowLink).toBeVisible();
  await workflowLink.click();
  await expect(page).toHaveURL(new RegExp(`/workflows/${workflowId}$`));
  await expect(page.getByRole('heading', { name: 'Этапы Workflow' })).toBeVisible();
  await expect(page.getByTestId('workflow-current-stage')).toBeVisible();
  await expect(page.getByRole('progressbar', { name: /Прогресс Workflow/ })).toBeVisible();
});
