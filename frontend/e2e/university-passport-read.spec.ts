import { expect, test, type Page } from '@playwright/test';

const richId = '11111111-1111-4111-8111-111111111111';
const emptyId = '22222222-2222-4222-8222-222222222222';
const programId = '33333333-3333-4333-8333-333333333333';
const teacherId = '44444444-4444-4444-8444-444444444444';

async function login(page: Page, role: 'admin' | 'user') {
  const username = process.env[`E2E_${role.toUpperCase()}_USERNAME`];
  const password = process.env[`E2E_${role.toUpperCase()}_PASSWORD`];
  test.skip(!username || !password, `Set E2E_${role.toUpperCase()} credentials`);
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(username ?? '');
  await page.locator('input[name="password"]').fill(password ?? '');
  const mePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const me = await mePromise;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  return { authorization: me.request().headers().authorization, apiOrigin: new URL(me.url()).origin };
}

function bundle(id: string, filled: boolean) {
  const programs = filled ? Array.from({ length: 21 }, (_, index) => ({
    id: index === 0 ? programId : `${String(index + 1).padStart(8, '0')}-3333-4333-8333-333333333333`,
    name: `Программа ${index + 1}`, direction_name: 'ИТ', status: 'active',
    launch_date: null, responsible_name: null, teachers_count: 1, students_count: 1,
  })) : [];
  return {
    university: { id, name: filled ? 'Университет с данными' : 'Пустой университет', city: filled ? 'Москва' : null },
    programs,
    teachers: filled ? [{ id: teacherId, full_name: 'Мария Тестовая', email: 'teacher@example.test', position: 'Преподаватель', readiness: 'ready', next_qualification_date: null, programs: programs.slice(0, 1) }] : [],
    students_summary: { total: filled ? 1 : 0, active: filled ? 1 : 0, graduated: 0, by_status: filled ? { active: 1 } : {}, by_program: filled ? [{ program_id: programId, program_name: 'Программа 1', total: 1, active: 1, graduated: 0 }] : [] },
    products: filled ? [{ id: '66666666-6666-4666-8666-666666666666', name: 'Продукт Тест', version: '1.0', vendor_name: 'Вендор Тест', status: 'planned', license: null }] : [],
    licenses: filled ? [{ id: '77777777-7777-4777-8777-777777777777', license_number: 'LIC-1', product_name: 'Продукт Тест', vendor_name: 'Вендор Тест', signed_at: '2026-01-01', expires_at: '2027-01-01', status: 'active', transfer_status: 'pending', contract_number: null }] : [],
    documents: filled ? [{ id: '88888888-8888-4888-8888-888888888888', document_type: 'contract', title: 'Документ Тест', file_name: 'test.pdf', file_size: 1024, mime_type: 'application/pdf', signed_at: null, expires_at: null, status: 'archived', uploaded_by: 'admin', created_at: '2026-09-20T10:00:00Z' }] : [],
    meetings: [], responsibles: [], contracts: [],
    workflow_summary: { instance_id: null, template_name: null, current_stage: null, progress_percent: 0, overdue_stages: 0, next_due_date: null },
    last_interactions: [], health_score: null, recent_audit: null,
  };
}

function interceptPassport(page: Page, id: string, filled: boolean, teacherFailure = false) {
  const aggregate = bundle(id, filled);
  const requests = new Map<string, number>();
  void page.route('**/api/v1/**', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === `/api/v1/teachers/${teacherId}/passport`) return route.fulfill({ status: 200, contentType: 'application/json', headers: { 'access-control-allow-origin': new URL(page.url()).origin }, body: JSON.stringify({ teacher: { id: teacherId, university_id: id, full_name: 'Мария Тестовая', email: 'teacher@example.test', position: 'Преподаватель' }, university: { id, name: 'Университет с данными', city: 'Москва' }, qualifications: [], certificates: [], programs: [], readiness: 'ready', readiness_reasons: [], next_qualification_date: null }) });
    if (!path.includes(id)) return route.continue();
    requests.set(path, (requests.get(path) ?? 0) + 1);
    const pageNumber = Number(url.searchParams.get('page') ?? 1);
    let body: unknown;
    let status = 200;
    if (path.endsWith('/passport')) body = aggregate;
    else if (path.endsWith('/passport/programs')) body = { items: aggregate.programs.slice((pageNumber - 1) * 20, pageNumber * 20), page: pageNumber, page_size: 20, total: aggregate.programs.length };
    else if (path.endsWith('/passport/teachers')) {
      status = teacherFailure ? 503 : 200;
      body = teacherFailure ? { error: { code: 'SERVICE_UNAVAILABLE' } } : { items: aggregate.teachers, page: 1, page_size: 20, total: aggregate.teachers.length };
    } else if (path.endsWith('/students')) body = { items: filled ? [{ id: '55555555-5555-4555-8555-555555555555', external_id: 'student-1', university_id: id, program_id: programId, full_name: 'Иван Студент', group_name: null, status: 'active', started_at: '2026-09-01', finished_at: null, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z' }] : [], page: 1, page_size: 20, total: filled ? 1 : 0 };
    else if (path.endsWith('/meetings')) body = { items: filled ? [{ id: '99999999-9999-4999-8999-999999999999', university_id: id, meeting_type: 'online', subject: 'Встреча Тест', participants: [{ name: 'Мария Тестовая' }], outcome: null, next_action: null, next_action_due: null, meeting_at: '2026-09-20T10:00:00Z', created_by_keycloak_sub: 'admin', created_at: '2026-09-20T10:00:00Z', updated_at: '2026-09-20T10:00:00Z' }] : [], page: 1, page_size: 20, total: filled ? 1 : 0 };
    else if (path.endsWith('/health-score')) body = { university_id: id, score: filled ? 78 : 100, status: filled ? 'yellow' : 'green', breakdown: { tasks: 80, documents: 75, stages: 80, teachers: 75, launch: 80 }, reasons: [], calculated_at: '2026-09-20T10:00:00Z', input_counters: {} };
    else if (path.endsWith('/health-score/history')) body = [];
    else return route.continue();
    return route.fulfill({ status, contentType: 'application/json', headers: { 'access-control-allow-origin': new URL(page.url()).origin }, body: JSON.stringify(body) });
  });
  return requests;
}

for (const role of ['admin', 'user'] as const) {
  test(`real backend rejects an unknown University for ${role}`, async ({ page }) => {
    const auth = await login(page, role);
    const response = await page.request.get(`${auth.apiOrigin}/api/v1/universities/${emptyId}/passport`, { headers: { Authorization: auth.authorization } });
    expect(response.status()).toBe(role === 'admin' ? 404 : 403);
  });
}

test('populated Passport uses paginated reads and one cached aggregate', async ({ page }) => {
  await login(page, 'admin');
  const requests = interceptPassport(page, richId, true);
  await page.goto(`/universities/${richId}`);
  await expect(page.getByRole('heading', { name: 'Университет с данными', level: 1 })).toBeVisible();
  await page.getByRole('tab', { name: 'Программы' }).click();
  await expect(page.getByText('Программа 1', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Далее' }).click();
  await expect(page.getByText('Программа 21', { exact: true }).first()).toBeVisible();
  await page.getByRole('tab', { name: 'Преподаватели' }).click();
  await expect(page.getByText('Мария Тестовая').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Студенты' }).click();
  await expect(page.getByText('Иван Студент').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Продукты' }).click();
  await expect(page.getByText('Продукт Тест').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Лицензии' }).click();
  await expect(page.getByText('LIC-1').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Документы' }).click();
  await expect(page.getByText('Документ Тест').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Встречи' }).click();
  await expect(page.getByText('Встреча Тест').first()).toBeVisible();
  await page.getByRole('tab', { name: 'Health Score' }).click();
  await expect(page.getByText('Нет данных о динамике')).toBeVisible();
  await page.getByRole('tab', { name: 'Преподаватели' }).click();
  expect(requests.get(`/api/v1/universities/${richId}/passport`)).toBe(1);
  expect(requests.get(`/api/v1/universities/${richId}/passport/teachers`)).toBe(1);
  expect(requests.get(`/api/v1/universities/${richId}/health-score`)).toBe(1);
  await page.getByRole('link', { name: 'Открыть', exact: true }).first().click();
  await page.waitForURL((url) => url.pathname === `/teachers/${teacherId}`);
  await expect(page.getByRole('heading', { name: 'Мария Тестовая', level: 1 })).toBeVisible();
});

test('empty Passport keeps header and isolated empty sections', async ({ page }) => {
  await login(page, 'admin');
  interceptPassport(page, emptyId, false);
  await page.goto(`/universities/${emptyId}`);
  await expect(page.getByRole('heading', { name: 'Пустой университет', level: 1 })).toBeVisible();
  await page.getByRole('tab', { name: 'Преподаватели' }).click();
  await expect(page.getByText('Нет преподавателей с выбранным статусом')).toBeVisible();
  await page.getByRole('tab', { name: 'Документы' }).click();
  await expect(page.getByText('Документы пока не добавлены')).toBeVisible();
});

test('section error does not remove the Passport header', async ({ page }) => {
  await login(page, 'admin');
  interceptPassport(page, richId, true, true);
  await page.goto(`/universities/${richId}?tab=teachers`);
  await expect(page.getByRole('heading', { name: 'Университет с данными', level: 1 })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Повторить' })).toBeVisible();
});
