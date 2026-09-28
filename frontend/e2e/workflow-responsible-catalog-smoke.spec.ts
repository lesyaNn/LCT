import { expect, test } from '@playwright/test';
import { createIsolatedWorkflow, loginForWorkflowE2E } from './workflow-isolated-fixture';

test('stage assignments and catalog university picker persist on disposable stand', async ({ page, request }) => {
  test.skip(process.env.E2E_DISPOSABLE_DB !== '1' || !process.env.E2E_WORKFLOW_UNIVERSITY_ID || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD,
    'Requires a disposable seeded stand and admin credentials.');
  const universityId = process.env.E2E_WORKFLOW_UNIVERSITY_ID!;
  const authorization = await loginForWorkflowE2E(page);
  const instanceId = await createIsolatedWorkflow(request, authorization, '14 этапов');
  const apiBase = process.env.E2E_API_URL ?? 'http://localhost:8000';
  const headers = { authorization };
  const passport = await (await request.get(`${apiBase}/api/v1/universities/${universityId}/passport`, { headers })).json();
  const people = (passport.responsibles as Array<{ id: string; full_name: string }>).slice(0, 3);
  expect(people).toHaveLength(3);
  const detail = async () => {
    const response = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}`, { headers });
    expect(response.status()).toBe(200);
    return response.json() as Promise<{ responsible_id: string | null; stages: Array<{ id: string; responsible_id: string | null; effective_responsible_id: string | null }> }>;
  };
  await page.goto(`/workflows/${instanceId}`);
  const global = page.getByRole('button', { name: 'Назначить на весь Workflow' });
  const setGlobal = async (person: typeof people[number]) => {
    await global.click();
    const dialog = page.getByRole('dialog', { name: 'Ответственный Workflow' });
    await dialog.getByRole('combobox').selectOption(person.id);
    await dialog.getByRole('button', { name: 'Сохранить' }).click();
    await expect(dialog).toHaveCount(0);
  };
  const stageButtons = page.locator('section[aria-labelledby$="-stages-title"] ol > li > button');
  await expect(stageButtons).toHaveCount(14);
  await setGlobal(people[0]);
  const stage = async (index: number) => {
    await stageButtons.nth(index - 1).click();
    return page.locator('section[aria-labelledby$="-overview-title"]');
  };
  const setStage = async (personId: string | null) => {
    const overview = await stage(5);
    await overview.getByRole('button', { name: 'Редактировать ответственного этапа' }).click();
    const dialog = page.getByRole('dialog', { name: 'Ответственный этого этапа' });
    await dialog.getByRole('combobox').selectOption(personId ?? '');
    await dialog.getByRole('button', { name: 'Сохранить' }).click();
    await expect(dialog).toHaveCount(0);
  };
  await setStage(people[1].id);
  let record = await detail();
  expect(record.stages.map((item) => item.effective_responsible_id)).toEqual(record.stages.map((_, index) => index === 4 ? people[1].id : people[0].id));
  await page.reload();
  await stage(5);
  await expect(page.locator('section[aria-labelledby$="-overview-title"]')).toContainText(people[1].full_name);
  await setStage(null);
  record = await detail();
  expect(record.stages[4].responsible_id).toBeNull();
  await setStage(people[1].id);
  await setGlobal(people[2]);
  record = await detail();
  expect(record.stages[3].effective_responsible_id).toBe(people[2].id);
  expect(record.stages[4].effective_responsible_id).toBe(people[1].id);
  expect(record.stages[5].effective_responsible_id).toBe(people[2].id);
  await page.reload();
  await stage(5);
  await expect(page.locator('section[aria-labelledby$="-overview-title"]')).toContainText('Для этого этапа');
  const activity = await (await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/activity`, { headers })).json() as Array<{ type: string }>;
  expect(activity.some((item) => item.type === 'responsible_changed')).toBeTruthy();
  expect(activity.some((item) => item.type === 'stage_responsible_changed')).toBeTruthy();

  await page.goto('/admin/catalogs');
  await page.locator('#catalog-tab-responsibles').click();
  await page.getByRole('searchbox', { name: 'Поиск' }).fill(people[0].full_name);
  const edit = page.getByRole('button', { name: `Изменить ${people[0].full_name}` });
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await edit.click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: 'ВУЗы' }).click();
    const search = page.getByRole('searchbox', { name: 'Поиск в поле «ВУЗы»' });
    const menu = search.locator('../..');
    await expect(menu).toBeVisible();
    const box = await menu.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(901);
    expect(await menu.evaluate((element) => element.scrollHeight > element.clientHeight)).toBeTruthy();
    expect(await menu.evaluate((element) => element.parentElement?.getAttribute('role'))).toBe('presentation');
    if (width === 390) {
      await menu.locator('label').filter({ has: page.locator('input[type="checkbox"]:not(:checked)') }).first().click();
      await dialog.getByRole('button', { name: 'Сохранить' }).click();
      await expect(dialog).toHaveCount(0);
      await page.reload();
      await page.locator('#catalog-tab-responsibles').click();
      await page.getByRole('button', { name: 'Фильтры' }).click();
      await page.getByRole('searchbox', { name: 'Поиск' }).fill(people[0].full_name);
      await page.getByRole('button', { name: 'Показать результаты' }).click();
      await edit.click();
      await dialog.getByRole('button', { name: 'ВУЗы' }).click();
      await expect.poll(() => page.getByRole('searchbox', { name: 'Поиск в поле «ВУЗы»' }).locator('../..').locator('input[type="checkbox"]:checked').count()).toBeGreaterThan(1);
    }
    await dialog.getByRole('button', { name: 'Закрыть' }).click();
  }
});
