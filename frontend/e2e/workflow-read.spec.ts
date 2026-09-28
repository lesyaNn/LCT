import { expect, test, type Page } from '@playwright/test';

const universityId = '11111111-1111-4111-8111-111111111111';
const firstProgram = '22222222-2222-4222-8222-222222222222';
const secondProgram = '33333333-3333-4333-8333-333333333333';
const instanceId = '44444444-4444-4444-8444-444444444444';
const firstStage = '55555555-5555-4555-8555-555555555555';
const secondStage = '66666666-6666-4666-8666-666666666666';
const firstTemplateStage = '77777777-7777-4777-8777-777777777777';
const secondTemplateStage = '88888888-8888-4888-8888-888888888888';
const now = '2026-09-20T10:00:00+03:00';

async function login(page: Page) {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E_ADMIN credentials');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
}

function instance() {
  return {
    id: instanceId, university_id: universityId, program_id: firstProgram,
    template_id: '99999999-9999-4999-8999-999999999999',
    university_name: 'Тестовый ВУЗ', university_city: 'Москва', program_name: 'Программа А',
    current_stage_id: secondTemplateStage, current_instance_stage_id: secondStage,
    responsible_id: null, status: 'active', due_date: null, completed_at: null,
    is_overdue: false, days_overdue: 0, created_at: now, updated_at: now,
    stages: [
      { id: firstStage, template_stage_id: firstTemplateStage, order_index: 1, name: 'Подготовка', description: null, is_required: true, status: 'completed', due_date: '2026-09-18', completed_at: now, is_overdue: false, days_overdue: 0, tasks_total: 1, tasks_completed: 1, created_at: now, updated_at: now },
      { id: secondStage, template_stage_id: secondTemplateStage, order_index: 2, name: 'Запуск', description: null, is_required: true, status: 'pending', due_date: null, completed_at: null, is_overdue: false, days_overdue: 0, tasks_total: 1, tasks_completed: 0, created_at: now, updated_at: now },
    ],
  };
}

async function stubReads(page: Page) {
  const calls = new Map<string, number>();
  const taskRows = [
    { id: 'aaaaaaa1-aaaa-4aaa-8aaa-aaaaaaaaaaaa', instance_id: instanceId, stage_id: firstTemplateStage, title: 'Завершённая задача', status: 'done', responsible_id: null, deadline: null, completed_at: now },
    { id: 'aaaaaaa2-aaaa-4aaa-8aaa-aaaaaaaaaaaa', instance_id: instanceId, stage_id: secondTemplateStage, title: 'Открытая задача', status: 'open', responsible_id: null, deadline: null, completed_at: null },
  ];
  const instanceWithTasks = () => {
    const record = instance();
    record.stages = record.stages.map((stage) => ({ ...stage, tasks_total: taskRows.filter((task) => task.stage_id === stage.template_stage_id).length, tasks_completed: taskRows.filter((task) => task.stage_id === stage.template_stage_id && task.status === 'done').length }));
    return record;
  };
  await page.route('**/api/v1/**', async (route) => {
    const method = route.request().method();
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown;
    if (path.startsWith(`/api/v1/workflow/instances/${instanceId}/tasks`) && method !== 'GET') {
      const id = path.split('/').at(-1);
      if (method === 'POST') {
        const input = route.request().postDataJSON() as { stage_id: string; title: string };
        const task = { id: 'aaaaaaa3-aaaa-4aaa-8aaa-aaaaaaaaaaaa', instance_id: instanceId, stage_id: input.stage_id, title: input.title, status: 'open', responsible_id: null, deadline: null, completed_at: null };
        taskRows.push(task);
        return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(task) });
      }
      const task = taskRows.find((row) => row.id === id);
      if (method === 'PATCH' && task) {
        Object.assign(task, route.request().postDataJSON());
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(task) });
      }
      if (method === 'DELETE' && task) {
        taskRows.splice(taskRows.indexOf(task), 1);
        return route.fulfill({ status: 204 });
      }
    }
    if (method !== 'GET') return route.continue();
    if (path === `/api/v1/universities/${universityId}/passport`) body = {
      university: { id: universityId, name: 'Тестовый ВУЗ', city: 'Москва' },
      programs: [],
      products: [], licenses: [], documents: [], meetings: [], responsibles: [], contracts: [],
      workflow_summary: { instance_id: null, template_name: null, current_stage: null, progress_percent: 0, overdue_stages: 0, next_due_date: null },
      last_interactions: [], recent_audit: null,
    };
    else if (path === `/api/v1/universities/${universityId}/passport/programs`) body = { items: [
      { id: firstProgram, name: 'Программа А', direction_name: 'ИТ', status: 'active', launch_date: null, responsible_name: null },
      { id: secondProgram, name: 'Программа Б', direction_name: 'ИТ', status: 'planned', launch_date: null, responsible_name: null },
    ], page: 1, page_size: 100, total: 2 };
    else if (path === '/api/v1/workflow/instances') body = { items: [instanceWithTasks()], page: 1, page_size: 100, total: 1 };
    else if (path === `/api/v1/workflow/instances/${instanceId}`) body = instanceWithTasks();
    else if (path === `/api/v1/workflow/instances/${instanceId}/tasks`) body = { items: taskRows, page: 1, page_size: 100, total: taskRows.length };
    else if (path === `/api/v1/workflow/instances/${instanceId}/comments`) body = { items: [
      { id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', instance_id: instanceId, stage_id: secondTemplateStage, author_keycloak_sub: 'author-sub', content: 'Реальный комментарий', is_internal: true, created_at: now, updated_at: now },
    ], page: 1, page_size: 100, total: 1 };
    else if (path === `/api/v1/workflow/instances/${instanceId}/attachments`) body = { items: [
      { id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', instance_id: instanceId, stage_id: secondTemplateStage, original_filename: 'workflow.pdf', mime_type: 'application/pdf', file_size: 12, uploaded_by_keycloak_sub: 'author-sub', created_at: now, updated_at: now },
    ], page: 1, page_size: 100, total: 1 };
    else if (path === `/api/v1/workflow/instances/${instanceId}/transitions`) body = [
      { id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', instance_id: instanceId, from_stage_id: firstTemplateStage, to_stage_id: secondTemplateStage, actor_keycloak_sub: 'author-sub', comment: 'Этап завершён', created_at: now },
    ];
    else if (path === `/api/v1/workflow/instances/${instanceId}/allowed-transitions`) body = [];
    else if (path === `/api/v1/workflow/instances/${instanceId}/rollback-targets`) body = [];
    else if (path === `/api/v1/workflow/instances/${instanceId}/attachments/cccccccc-cccc-4ccc-8ccc-cccccccccccc/download`) {
      return route.fulfill({ status: 200, contentType: 'application/pdf', headers: { 'access-control-allow-origin': new URL(page.url()).origin, 'content-disposition': 'attachment; filename="workflow.pdf"' }, body: '%PDF-1.4 test' });
    } else return route.continue();
    calls.set(path, (calls.get(path) ?? 0) + 1);
    return route.fulfill({ status: 200, contentType: 'application/json', headers: { 'access-control-allow-origin': new URL(page.url()).origin }, body: JSON.stringify(body) });
  });
  return calls;
}

test('Workflow lists university instances and never commits mock mutations', async ({ page }) => {
  await login(page);
  const calls = await stubReads(page);
  await page.goto(`/universities/${universityId}?tab=workflow`);
  await expect(page.getByRole('heading', { name: 'Workflow вуза' })).toBeVisible();
  const workflowCard = page.getByRole('link', { name: /Программа А/ });
  await expect(workflowCard.getByText('В работе')).toHaveClass(/brand/);
  await expect(workflowCard.getByText('Открыть Workflow')).toHaveCount(0);
  await expect(workflowCard.getByText(/Ответственный:/)).toHaveCount(0);
  await workflowCard.click();
  await page.waitForURL((url) => url.pathname === `/workflows/${instanceId}`);
  await page.goBack();
  await workflowCard.focus();
  await page.keyboard.press('Space');
  await page.waitForURL((url) => url.pathname === `/workflows/${instanceId}`);
  await page.goBack();
  await workflowCard.focus();
  await page.keyboard.press('Enter');
  await page.waitForURL((url) => url.pathname === `/workflows/${instanceId}`);
  await expect(page.getByText('Запуск', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('Открытая задача')).toBeVisible();
  await page.getByRole('button', { name: '+ Добавить задачу' }).click();
  await page.getByRole('textbox', { name: 'Новая задача' }).fill('Проверить договор');
  await page.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText('Проверить договор')).toBeVisible();
  await expect(page.getByText('0 из 2 выполнено')).toBeVisible();
  await page.getByRole('checkbox', { name: 'Выполнено: Проверить договор' }).check();
  await expect(page.getByText('1 из 2 выполнено')).toBeVisible();
  const createdTask = page.getByRole('listitem').filter({ hasText: 'Проверить договор' });
  await createdTask.getByRole('button', { name: 'Редактировать задачу «Проверить договор»' }).click();
  await createdTask.getByRole('textbox', { name: 'Название задачи' }).fill('Проверить лицензию');
  await createdTask.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Проверить лицензию')).toBeVisible();
  await page.getByRole('listitem').filter({ hasText: 'Проверить лицензию' }).getByRole('button', { name: 'Удалить задачу «Проверить лицензию»' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить' }).click();
  await expect(page.getByText('Проверить лицензию')).toHaveCount(0);
  await page.locator('details').filter({ has: page.getByText('История Workflow', { exact: true }) }).first().locator('summary').first().click();
  await page.locator('details details').filter({ has: page.getByText('Запуск', { exact: true }) }).first().locator('summary').click();
  await expect(page.getByText('Реальный комментарий')).toBeVisible();
  await expect(page.getByText('workflow.pdf')).toBeVisible();
  await expect(page.getByText('Доступные переходы')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Перевести на следующий этап' })).toHaveCount(0);
  await page.getByRole('button', { name: /Подготовка/ }).first().click();
  await expect(page.getByText('Завершённая задача')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Сохранить' })).toHaveCount(0);
  await page.getByRole('button', { name: /Запуск/ }).first().click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать workflow.pdf' }).click();
  expect((await download).suggestedFilename()).toBe('workflow.pdf');
  expect(calls.get('/api/v1/workflow/instances')).toBeGreaterThanOrEqual(1);
});

test('Workflow stage emphasis remains clear at responsive widths', async ({ page }) => {
  test.skip(process.env.E2E_MOCK_MODE !== '1', 'Run against a dev server with mock auth and data.');
  await page.goto('/workflows/university-014');
  await expect(page.getByRole('heading', { name: 'Этапы Workflow' })).toBeVisible();
  const current = page.getByTestId('workflow-current-stage');
  const stages = page.locator('section[aria-labelledby$="-stages-title"] button[aria-controls]');
  await expect(current).toHaveAttribute('aria-current', 'step');
  await expect(page.locator('main header').first().getByText('Текущий этап', { exact: true })).toHaveCount(0);

  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const initial = await page.evaluate(() => {
      const progress = document.querySelector('[role="progressbar"] > span');
      const selected = document.querySelector('button[aria-expanded="true"][aria-controls]');
      const currentButton = document.querySelector('[data-testid="workflow-current-stage"]');
      if (!progress || !selected || !currentButton) throw new Error('Workflow controls are missing');
      return {
        progress: getComputedStyle(progress).backgroundColor,
        selectedLeft: getComputedStyle(selected).borderLeftColor,
        selectedTop: getComputedStyle(selected).borderTopColor,
        currentMarker: getComputedStyle(currentButton.querySelector('span')!).backgroundColor,
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
      };
    });
    expect(initial.progress).toBe(initial.selectedLeft);
    expect(initial.currentMarker).toBe(initial.progress.replace('rgb(', 'rgba(').replace(')', ', 0.1)'));
    expect(initial.selectedTop).toBe('rgba(0, 0, 0, 0)');
    expect(initial.documentWidth).toBeLessThanOrEqual(initial.viewportWidth + 2);
    await stages.first().click();
    await expect(stages.first()).toHaveAttribute('aria-expanded', 'true');
    await expect(current).toHaveAttribute('aria-current', 'step');
    const selectedOtherStage = await stages.first().evaluate((button) => ({
      left: getComputedStyle(button).borderLeftColor,
      top: getComputedStyle(button).borderTopColor,
    }));
    expect(selectedOtherStage.left).toBe(initial.progress);
    expect(selectedOtherStage.top).toBe('rgba(0, 0, 0, 0)');
    await current.click();
  }
});
