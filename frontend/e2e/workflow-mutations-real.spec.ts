import { expect, test, type Page } from '@playwright/test';

const apiBase = process.env.E2E_API_URL ?? 'http://localhost:8000';

async function login(page: Page, username = process.env.E2E_ADMIN_USERNAME ?? '', password = process.env.E2E_ADMIN_PASSWORD ?? ''): Promise<string> {
  let bearer = '';
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/auth/me')) bearer = request.headers().authorization ?? bearer;
  });
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await expect.poll(() => bearer).not.toBe('');
  return bearer;
}

type PageResult<T> = { items: T[]; total: number };
type Template = { id: string; name: string; is_active: boolean };
type Instance = { id: string; university_id: string; program_id: string; current_instance_stage_id: string; stages: Array<{ id: string; name: string; order_index: number }> };

test('seeded real Workflow: create API, comment and transition UI, persist after reload', async ({ page, request }) => {
  test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for one-time local dev mutations');
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set demo admin credentials');
  test.skip(!process.env.E2E_WORKFLOW_UNIVERSITY_ID || !process.env.E2E_WORKFLOW_PROGRAM_ID, 'Select an unused pair from the official seed');
  const authorization = await login(page);
  const headers = { authorization };
  const universityId = process.env.E2E_WORKFLOW_UNIVERSITY_ID ?? '';
  const programId = process.env.E2E_WORKFLOW_PROGRAM_ID ?? '';
  const templatesResponse = await request.get(`${apiBase}/api/v1/workflow/templates?page=1&page_size=100`, { headers });
  expect(templatesResponse.ok()).toBeTruthy();
  const templates = (await templatesResponse.json()) as PageResult<Template>;
  const template = templates.items.find((item) => item.is_active);
  expect(template).toBeDefined();

  const lookup = await request.get(`${apiBase}/api/v1/workflow/instances/by-program/${programId}?university_id=${universityId}`, { headers });
  expect(lookup.ok()).toBeTruthy();
  const existing = (await lookup.json()) as Instance | null;
  test.skip(Boolean(existing && existing.stages.find((stage) => stage.id === existing.current_instance_stage_id)?.order_index !== 1), 'First transition already tested; do not move the seeded Workflow again');
  if (!template) return;

  const created = existing ? null : await request.post(`${apiBase}/api/v1/workflow/instances`, {
    headers, data: { university_id: universityId, program_id: programId, template_id: template.id },
  });
  if (created) expect(created.status()).toBe(201);
  const instance = existing ?? (await created!.json()) as Instance;
  expect(instance.program_id).toBe(programId);
  await page.goto(`/workflows/${instance.id}`);
  await expect(page.getByRole('button', { name: 'Перевести на следующий этап' })).toBeVisible();

  const commentText = `Stage 6 integration ${Date.now()}`;
  const commentRequests: string[] = [];
  const transitionRequests: string[] = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith(`/instances/${instance.id}/comments`)) commentRequests.push(request.url());
    if (request.method() === 'POST' && request.url().endsWith(`/instances/${instance.id}/transition`)) transitionRequests.push(request.url());
  });
  await page.getByLabel('Добавить комментарий').fill(commentText);
  await page.getByRole('button', { name: 'Отправить' }).click();
  await expect(page.getByText(commentText)).toBeVisible();
  expect(commentRequests).toHaveLength(1);
  await page.reload();
  await expect(page.getByText(commentText)).toBeVisible();

  await page.getByRole('button', { name: 'Перевести на следующий этап' }).click();
  await expect(page.getByRole('dialog', { name: 'Перевести на следующий этап' })).toBeVisible();
  await page.getByRole('dialog').getByRole('textbox', { name: 'Комментарий' }).fill('Проверка реального перехода Workflow');
  await page.getByRole('button', { name: 'Перевести', exact: true }).click();
  await expect(page.getByText('Этап успешно переведён')).toBeVisible();
  expect(transitionRequests).toHaveLength(1);
  const detailResponse = await request.get(`${apiBase}/api/v1/workflow/instances/${instance.id}`, { headers });
  expect(detailResponse.ok()).toBeTruthy();
  const updated = (await detailResponse.json()) as Instance;
  expect(updated.current_instance_stage_id).not.toBe(instance.current_instance_stage_id);
  await page.reload();
  await expect(page.getByTestId('workflow-current-stage')).toContainText(updated.stages.find((item) => item.id === updated.current_instance_stage_id)?.name ?? '');
});

for (const role of ['manager', 'user'] as const) {
  test(`demo ${role} cannot mutate an unassigned Workflow`, async ({ page, request }) => {
    test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for local dev permissions check');
    test.skip(!process.env.E2E_WORKFLOW_INSTANCE_ID, 'Set the test-created Workflow ID');
    const username = process.env[`E2E_${role.toUpperCase()}_USERNAME`] ?? role;
    const password = process.env[`E2E_${role.toUpperCase()}_PASSWORD`] ?? `${role}123`;
    const authorization = await login(page, username, password);
    const instanceId = process.env.E2E_WORKFLOW_INSTANCE_ID ?? '';
    const detail = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}`, { headers: { authorization } });
    expect(detail.status()).toBe(403);
    await page.goto(`/workflows/${instanceId}`);
    await expect(page.getByRole('button', { name: 'Перевести на следующий этап' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Отправить' })).toHaveCount(0);
  });
}

test('seeded real Kanban: cancel keeps stage, confirm moves once', async ({ page, request }) => {
  test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for one-time local dev mutations');
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD || !process.env.E2E_WORKFLOW_INSTANCE_ID, 'Set admin and the test-created Workflow ID');
  const authorization = await login(page);
  const instanceId = process.env.E2E_WORKFLOW_INSTANCE_ID ?? '';
  const headers = { authorization };
  const read = async () => (await (await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}`, { headers })).json()) as Instance;
  const before = await read();
  const currentOrder = before.stages.find((stage) => stage.id === before.current_instance_stage_id)?.order_index;
  if (currentOrder === 3) {
    await page.goto('/workflows');
    await page.getByRole('tab', { name: 'Доска' }).click();
    await expect(page.getByRole('heading', { name: before.stages.find((stage) => stage.id === before.current_instance_stage_id)?.name ?? '' })).toBeVisible();
    await page.getByRole('link', { name: 'Открыть / перевести' }).first().click();
    await expect(page).toHaveURL(new RegExp(`/workflows/${instanceId}$`));
    return;
  }
  test.skip(currentOrder !== 2, 'Kanban transition already tested; do not move again');
  const allowedResponse = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/allowed-transitions`, { headers });
  expect(allowedResponse.ok()).toBeTruthy();
  const allowed = (await allowedResponse.json()) as Array<{ id: string; name: string }>;
  expect(allowed.length).toBeGreaterThan(0);
  await page.goto('/workflows');
  await page.getByRole('tab', { name: 'Доска' }).click();
  const handle = page.getByRole('button', { name: /Переместить:/ });
  const target = page.locator('section[aria-label]').filter({ has: page.getByRole('heading', { name: allowed[0].name, exact: true }) });
  const drag = async () => {
    const source = await handle.boundingBox();
    const destination = await target.boundingBox();
    expect(source).not.toBeNull();
    expect(destination).not.toBeNull();
    const from = { x: source!.x + source!.width / 2, y: source!.y + source!.height / 2 };
    const to = { x: destination!.x + destination!.width / 2, y: destination!.y + destination!.height / 2 };
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(from.x + 12, from.y + 12, { steps: 5 });
    await page.mouse.move(to.x, to.y, { steps: 15 });
    await page.mouse.up();
  };
  await drag();
  await expect(page.getByRole('dialog', { name: 'Перевести на следующий этап' })).toBeVisible();
  await page.getByRole('dialog').getByRole('button', { name: 'Отмена' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect((await read()).current_instance_stage_id).toBe(before.current_instance_stage_id);
  await drag();
  await expect(page.getByRole('dialog', { name: 'Перевести на следующий этап' })).toBeVisible();
  await page.getByRole('dialog').getByRole('textbox', { name: 'Комментарий' }).fill('Переход с доски Workflow после подтверждения');
  await page.getByRole('dialog').getByRole('button', { name: 'Перевести', exact: true }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  const after = await read();
  expect(after.current_instance_stage_id).toBe(allowed[0].id);
  await page.reload();
  await page.getByRole('tab', { name: 'Доска' }).click();
  await expect(page.getByRole('heading', { name: allowed[0].name, exact: true })).toBeVisible();
});

test('real comment edit/delete and upload-audit reproduction', async ({ page, request }) => {
  test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for local dev mutations');
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD || !process.env.E2E_WORKFLOW_INSTANCE_ID, 'Set admin and the test-created Workflow ID');
  const authorization = await login(page);
  const instanceId = process.env.E2E_WORKFLOW_INSTANCE_ID ?? '';
  const headers = { authorization };
  const beforeFilesResponse = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments`, { headers });
  expect(beforeFilesResponse.ok()).toBeTruthy();
  const beforeFiles = (await beforeFilesResponse.json()) as PageResult<unknown>;
  await page.goto(`/workflows/${instanceId}`);
  const original = `Комментарий для редактирования ${Date.now()}`;
  const edited = `${original} — исправлен`;
  await page.getByRole('textbox', { name: 'Добавить комментарий' }).fill(original);
  await page.getByRole('button', { name: 'Отправить' }).click();
  await expect(page.getByText(original)).toBeVisible();
  await page.getByRole('button', { name: /Редактировать комментарий/ }).first().click();
  await page.getByRole('textbox', { name: 'Редактировать комментарий' }).fill(edited);
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  await expect(page.getByText(edited)).toBeVisible();
  await page.reload();
  await expect(page.getByText(edited)).toBeVisible();
  await page.getByRole('button', { name: /Удалить комментарий/ }).first().click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(page.getByText(edited)).toHaveCount(0);

  const uploadResponse = page.waitForResponse((response) => response.request().method() === 'POST'
    && response.url().endsWith(`/instances/${instanceId}/attachments`));
  await page.getByLabel('Выбрать файлы для загрузки').setInputFiles({
    name: 'stage6-upload-check.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\nStage 6 local test\n'),
  });
  const upload = await uploadResponse;
  expect(upload.status()).toBe(409);
  const error = await upload.json() as { error?: { details?: { field?: string } } };
  expect(error.error?.details?.field).toBe('entity_id');
  await expect(page.getByText('Ошибка загрузки')).toBeVisible();
  const afterFilesResponse = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments`, { headers });
  expect(afterFilesResponse.ok()).toBeTruthy();
  const afterFiles = (await afterFilesResponse.json()) as PageResult<unknown>;
  expect(afterFiles.total).toBe(beforeFiles.total);
});
