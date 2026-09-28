import { expect, test } from '@playwright/test';
import { loginForWorkflowE2E } from './workflow-isolated-fixture';

test('passport starts a real Workflow and admin lists share responsive toolbar layout', async ({ page, request }) => {
  test.skip(process.env.E2E_DISPOSABLE_DB !== '1' || !process.env.E2E_WORKFLOW_UNIVERSITY_ID || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD,
    'Requires a disposable seeded stand and admin credentials.');
  const universityId = process.env.E2E_WORKFLOW_UNIVERSITY_ID!;
  const authorization = await loginForWorkflowE2E(page);
  const apiBase = process.env.E2E_API_URL ?? 'http://localhost:8000';
  const headers = { authorization };
  const directions = await (await request.get(`${apiBase}/api/v1/directions?page=1&page_size=1`, { headers })).json() as { items: Array<{ id: string }> };
  const programName = `Overview E2E ${crypto.randomUUID()}`;
  const programResponse = await request.post(`${apiBase}/api/v1/programs`, { headers, data: { direction_id: directions.items[0].id, name: programName } });
  expect(programResponse.status()).toBe(201);
  const program = await programResponse.json() as { id: string };
  expect((await request.post(`${apiBase}/api/v1/universities/${universityId}/programs`, { headers, data: { program_id: program.id } })).status()).toBe(201);

  await page.goto(`/universities/${universityId}?tab=overview`);
  const card = page.getByRole('article').filter({ hasText: programName });
  await expect(card).toContainText('Workflow не запущен');
  await expect(card).not.toContainText('В работе');
  await expect(card).not.toContainText('Ответственный');
  await card.getByRole('button', { name: 'Запустить Workflow' }).click();
  const modal = page.getByRole('dialog', { name: 'Создание Workflow' });
  await expect(modal.getByRole('combobox', { name: 'Программа обучения' })).toHaveValue(program.id);
  await modal.getByRole('combobox', { name: 'Шаблон Workflow' }).selectOption({ index: 1 });
  await modal.getByRole('button', { name: 'Создать Workflow' }).click();
  await expect(modal).toHaveCount(0);
  await expect(card).toContainText('В работе');
  const link = card.getByRole('link', { name: 'Открыть Workflow' });
  await expect(link).toHaveAttribute('href', /\/workflows\/[^/]+$/);
  await link.click();
  await expect(page).toHaveURL(/\/workflows\/[^/]+$/);

  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, heading] of [['/admin/users', 'Пользователи и права'], ['/admin/catalogs', 'Управление каталогами']] as const) {
      await page.goto(path);
      await expect(page.getByRole('heading', { name: heading })).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
      if (path === '/admin/users') {
        if (width > 900) await expect(page.getByRole('region', { name: 'Фильтры пользователей' }).getByRole('button', { name: 'Создать приглашение' })).toBeVisible();
        else {
          await page.getByRole('button', { name: /^Фильтры/ }).click();
          await expect(page.getByRole('dialog', { name: 'Фильтры' }).getByRole('button', { name: 'Создать приглашение' })).toBeVisible();
          await page.getByRole('dialog', { name: 'Фильтры' }).getByRole('button', { name: 'Закрыть' }).click();
        }
        await page.getByRole('button', { name: 'Настроить' }).first().click();
        const editor = page.getByRole('dialog', { name: 'Настройки пользователя' });
        await expect(editor.getByText('Скоуп данных')).toBeVisible();
        await expect(editor.getByRole('button', { name: 'Сохранить' })).toBeVisible();
        await editor.getByRole('button', { name: 'Закрыть' }).click();
      }
    }
    await page.goto(`/universities/${universityId}?tab=overview`);
    await expect(page.getByRole('article').filter({ hasText: programName })).toContainText('В работе');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
  }
});
