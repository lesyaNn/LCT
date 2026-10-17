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
let isolatedProgramId = '';
let isolatedInstanceId = '';
const workflowProgramId = () => isolatedProgramId || process.env.E2E_WORKFLOW_PROGRAM_ID || '';
const workflowInstanceId = () => isolatedInstanceId || process.env.E2E_WORKFLOW_INSTANCE_ID || '';

test.beforeAll(async ({ browser, request }) => {
  if (process.env.E2E_WORKFLOW_ISOLATED !== '1' || process.env.E2E_WORKFLOW_MUTATIONS !== '1') return;
  const universityId = process.env.E2E_WORKFLOW_UNIVERSITY_ID ?? '';
  expect(universityId, 'Use a university outside the manager/user scope on the disposable stand.').not.toBe('');
  const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' });
  try {
    const page = await context.newPage();
    const authorization = await login(page);
    const headers = { authorization };
    const get = async (path: string) => {
      const response = await request.get(`${apiBase}/api/v1${path}`, { headers });
      expect(response.status(), `${path}: ${await response.text()}`).toBe(200);
      return response.json() as Promise<Record<string, unknown>>;
    };
    const post = async (path: string, data: Record<string, unknown>) => {
      const response = await request.post(`${apiBase}/api/v1${path}`, { headers, data });
      expect(response.status(), `${path}: ${await response.text()}`).toBe(201);
      return response.json() as Promise<Record<string, unknown>>;
    };
    const directions = await get('/directions?page=1&page_size=1');
    const direction = (directions.items as Array<{ id: string }>)[0];
    expect(direction?.id).toBeTruthy();
    const templates = await get('/workflow/templates?page=1&page_size=100');
    const template = (templates.items as Template[]).find((item) => item.is_active);
    expect(template).toBeDefined();
    const program = await post('/programs', { direction_id: direction.id, name: `Final Workflow E2E ${Date.now()}` });
    isolatedProgramId = String(program.id);
    await post(`/universities/${universityId}/programs`, { program_id: isolatedProgramId });
    const instance = await post('/workflow/instances', {
      university_id: universityId, program_id: isolatedProgramId, template_id: template!.id,
    });
    isolatedInstanceId = String(instance.id);
  } finally {
    await context.close();
  }
});

test('seeded real Workflow: create API, comment and transition UI, persist after reload', async ({ page, request }) => {
  test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for one-time local dev mutations');
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set demo admin credentials');
  test.skip(!process.env.E2E_WORKFLOW_UNIVERSITY_ID || !workflowProgramId(), 'Select an unused pair from the official seed');
  const authorization = await login(page);
  const headers = { authorization };
  const universityId = process.env.E2E_WORKFLOW_UNIVERSITY_ID ?? '';
  const programId = workflowProgramId();
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
    test.skip(!workflowInstanceId(), 'Set the test-created Workflow ID');
    const username = process.env[`E2E_${role.toUpperCase()}_USERNAME`] ?? role;
    const password = process.env[`E2E_${role.toUpperCase()}_PASSWORD`] ?? `${role}123`;
    const authorization = await login(page, username, password);
    const instanceId = workflowInstanceId();
    const detail = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}`, { headers: { authorization } });
    expect(detail.status()).toBe(403);
    await page.goto(`/workflows/${instanceId}`);
    await expect(page.getByRole('button', { name: 'Перевести на следующий этап' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Отправить' })).toHaveCount(0);
  });
}

test('seeded real Kanban: cancel keeps stage, confirm moves once', async ({ page, request }) => {
  test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for one-time local dev mutations');
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD || !workflowInstanceId(), 'Set admin and the test-created Workflow ID');
  const authorization = await login(page);
  const instanceId = workflowInstanceId();
  const headers = { authorization };
  const read = async () => (await (await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}`, { headers })).json()) as Instance;
  const before = await read();
  const currentOrder = before.stages.find((stage) => stage.id === before.current_instance_stage_id)?.order_index;
  if (currentOrder === 3) {
    await page.goto('/workflows');
    await page.getByRole('tab', { name: 'Канбан' }).click();
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
  const allowedRequests: string[] = [];
  page.on('request', (outgoing) => {
    if (outgoing.method() === 'GET' && outgoing.url().includes('/allowed-transitions')) allowedRequests.push(outgoing.url());
  });
  await page.goto('/workflows');
  await page.getByRole('tab', { name: 'Канбан' }).click();
  await expect(page.locator('article').filter({ has: page.locator(`a[href="/workflows/${instanceId}"]`) })).toBeVisible();
  expect(allowedRequests, 'Kanban must not fetch allowed transitions for every card on load').toHaveLength(0);
  const handle = page.locator('article').filter({ has: page.locator(`a[href="/workflows/${instanceId}"]`) })
    .getByRole('button', { name: /Переместить:/ });
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
  expect(allowedRequests).toHaveLength(1);
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
  await page.getByRole('tab', { name: 'Канбан' }).click();
  await expect(page.getByRole('heading', { name: allowed[0].name, exact: true })).toBeVisible();
});

test('real comment edit/delete and attachment upload/download/delete', async ({ page, request }) => {
  test.skip(process.env.E2E_WORKFLOW_MUTATIONS !== '1', 'Opt in for local dev mutations');
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD || !workflowInstanceId(), 'Set admin and the test-created Workflow ID');
  const authorization = await login(page);
  const instanceId = workflowInstanceId();
  const headers = { authorization };
  const leftovers = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments`, { headers });
  const leftoverFiles = (await leftovers.json()) as PageResult<{ id: string; original_filename: string }>;
  for (const file of leftoverFiles.items.filter((item) => item.original_filename === 'stage6-upload-check.pdf')) {
    expect((await request.delete(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments/${file.id}`, { headers })).status()).toBe(204);
  }
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
  expect(upload.status()).toBe(201);
  const file = await upload.json() as { id: string };
  await expect(page.getByText('stage6-upload-check.pdf')).toBeVisible();
  await page.reload();
  await expect(page.getByText('stage6-upload-check.pdf')).toBeVisible();
  const afterFilesResponse = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments`, { headers });
  expect(afterFilesResponse.ok()).toBeTruthy();
  const afterFiles = (await afterFilesResponse.json()) as PageResult<unknown>;
  expect(afterFiles.total).toBe(beforeFiles.total + 1);
  const download = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments/${file.id}/download`, { headers });
  expect(download.ok()).toBeTruthy();
  expect((await download.body()).toString()).toContain('Stage 6 local test');
  await page.getByRole('button', { name: 'Удалить stage6-upload-check.pdf' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(page.getByText('stage6-upload-check.pdf')).toHaveCount(0);
  const afterDelete = await request.get(`${apiBase}/api/v1/workflow/instances/${instanceId}/attachments`, { headers });
  expect(((await afterDelete.json()) as PageResult<unknown>).total).toBe(beforeFiles.total);
});
