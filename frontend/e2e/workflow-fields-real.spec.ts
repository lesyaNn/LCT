import { expect, test } from '@playwright/test';

test('Workflow responsible and current-stage due date persist after reload', async ({ page }) => {
  const instanceId = process.env.E2E_WORKFLOW_INSTANCE_ID;
  test.skip(!instanceId || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD,
    'Requires a writable Workflow instance and admin credentials.');

  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await page.goto(`/workflows/${instanceId}`);

  const info = page.locator('section[aria-labelledby$="-overview-title"]');
  const responsible = info.locator('div').filter({ has: page.getByText('Ответственный Workflow', { exact: true }) }).last();
  const deadline = info.locator('div').filter({ has: page.getByText('Дедлайн', { exact: true }) }).last();
  await responsible.getByRole('button', { name: /Назначить|Изменить/ }).click();
  const responsibleDialog = page.getByRole('dialog', { name: 'Ответственный Workflow' });
  const options = responsibleDialog.getByRole('combobox').locator('option');
  const originalResponsible = await responsibleDialog.getByRole('combobox').inputValue();
  await expect(options).not.toHaveCount(1);
  const candidates = (await options.evaluateAll((items) => items.map((item) => (item as HTMLOptionElement).value))).filter(Boolean);
  const first = candidates.find((value) => value !== originalResponsible);
  const second = candidates.find((value) => value !== originalResponsible && value !== first);
  expect(first).toBeTruthy();
  expect(second).toBeTruthy();
  await responsibleDialog.getByRole('combobox').selectOption(first!);
  await responsibleDialog.getByRole('button', { name: 'Сохранить' }).click();
  await expect(responsibleDialog).toHaveCount(0);
  const history = page.locator('section[aria-labelledby$="-transition-title"]');
  await expect(history.getByText('Ответственный изменён').first()).toBeVisible();
  await page.reload();
  await expect(responsible.getByRole('button', { name: 'Изменить' })).toBeVisible();
  await responsible.getByRole('button', { name: 'Изменить' }).click();
  await responsibleDialog.getByRole('combobox').selectOption(second!);
  await responsibleDialog.getByRole('button', { name: 'Сохранить' }).click();
  await page.reload();
  await responsible.getByRole('button', { name: 'Изменить' }).click();
  await expect(responsibleDialog.getByRole('combobox')).toHaveValue(second!);
  await responsibleDialog.getByRole('button', { name: 'Отмена' }).click();

  await expect(deadline.getByText('Срок не указан')).toHaveCount(0);
  await deadline.getByRole('button', { name: /Установить|Изменить/ }).click();
  const dateDialog = page.getByRole('dialog', { name: 'Дедлайн этапа' });
  const originalDate = await dateDialog.locator('input[type="date"]').inputValue();
  if (!originalDate) await expect(deadline.getByText('Не установлен')).toBeVisible();
  await dateDialog.locator('input[type="date"]').fill('2030-10-15');
  await dateDialog.getByRole('button', { name: 'Сохранить' }).click();
  await expect(history.getByText('Дедлайн изменён').first()).toBeVisible();
  await page.reload();
  await expect(deadline.getByRole('button', { name: 'Изменить' })).toBeVisible();
  await deadline.getByRole('button', { name: 'Изменить' }).click();
  await expect(dateDialog.locator('input[type="date"]')).toHaveValue('2030-10-15');
  await dateDialog.locator('input[type="date"]').fill('2030-10-20');
  await dateDialog.getByRole('button', { name: 'Сохранить' }).click();
  await page.reload();
  await deadline.getByRole('button', { name: 'Изменить' }).click();
  await expect(dateDialog.locator('input[type="date"]')).toHaveValue('2030-10-20');
  await dateDialog.locator('input[type="date"]').fill(originalDate);
  await dateDialog.getByRole('button', { name: 'Сохранить' }).click();
  await responsible.getByRole('button', { name: 'Изменить' }).click();
  await responsibleDialog.getByRole('combobox').selectOption(originalResponsible);
  await responsibleDialog.getByRole('button', { name: 'Сохранить' }).click();
});
