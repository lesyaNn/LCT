import { expect, test, type Page } from '@playwright/test';

const apiBase = process.env.E2E_API_URL ?? 'http://localhost:8000';
const universityId = process.env.E2E_PASSPORT_UNIVERSITY_ID ?? '';

async function login(page: Page, username = process.env.E2E_ADMIN_USERNAME ?? '', password = process.env.E2E_ADMIN_PASSWORD ?? ''): Promise<string> {
  let authorization = '';
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/auth/me')) authorization = request.headers().authorization ?? authorization;
  });
  await page.goto('/login');
  const keycloak = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloak.isVisible().catch(() => false)) await keycloak.click();
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await expect.poll(() => authorization).not.toBe('');
  return authorization;
}

test.beforeEach(() => {
  test.skip(process.env.E2E_PASSPORT_MUTATIONS !== '1', 'Opt in for local seeded Passport mutations');
  test.skip(!universityId || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set seeded university and demo admin');
});

test('seeded Passport opens and meeting create/edit/delete persists', async ({ page, request }) => {
  const authorization = await login(page);
  const subject = `Stage 7 встреча ${Date.now()}`;
  let meetingId = '';
  try {
    await page.goto(`/universities/${universityId}?tab=meetings`);
    await expect(page.getByRole('heading', { name: 'Встречи' })).toBeVisible();
    await page.getByRole('button', { name: 'Добавить встречу' }).click();
    const dialog = page.getByRole('dialog', { name: 'Добавить встречу' });
    await dialog.getByLabel('Тема *').fill(subject);
    const createResponse = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith(`/universities/${universityId}/meetings`));
    await dialog.getByRole('button', { name: 'Сохранить' }).click();
    const created = await createResponse;
    expect(created.status()).toBe(201);
    meetingId = ((await created.json()) as { id: string }).id;
    await expect(page.getByText(subject)).toBeVisible();
    await page.reload();
    await expect(page.getByText(subject)).toBeVisible();
    await page.getByRole('button', { name: 'Изменить' }).first().click();
    await page.getByRole('dialog', { name: 'Редактировать встречу' }).getByLabel('Тема *').fill(`${subject} — исправлена`);
    await page.getByRole('dialog').getByRole('button', { name: 'Сохранить' }).click();
    await expect(page.getByText(`${subject} — исправлена`)).toBeVisible();
    await page.reload();
    await expect(page.getByText(`${subject} — исправлена`)).toBeVisible();
    await page.getByRole('button', { name: 'Удалить' }).first().click();
    await page.getByRole('dialog', { name: 'Удалить встречу?' }).getByRole('button', { name: 'Удалить' }).click();
    await expect(page.getByText(`${subject} — исправлена`)).toHaveCount(0);
    meetingId = '';
  } finally {
    if (meetingId) await request.delete(`${apiBase}/api/v1/meetings/${meetingId}`, { headers: { authorization } });
  }
});

test('seeded Passport student create/edit/status persists', async ({ page, request }) => {
  const authorization = await login(page);
  const externalId = `stage7-${Date.now()}`;
  const name = `Студент ${externalId}`;
  let studentId = '';
  try {
    await page.goto(`/universities/${universityId}?tab=students`);
    await expect(page.getByRole('button', { name: 'Добавить студента' })).toBeVisible();
    await page.getByRole('button', { name: 'Добавить студента' }).click();
    const dialog = page.getByRole('dialog', { name: 'Добавить студента' });
    await dialog.getByLabel('Внешний ID *').fill(externalId);
    await expect(dialog.getByLabel('Программа *').locator('option')).not.toHaveCount(1);
    const programId = await dialog.getByLabel('Программа *').locator('option').nth(1).getAttribute('value');
    expect(programId).toBeTruthy();
    await dialog.getByLabel('Программа *').selectOption(programId ?? '');
    await dialog.getByLabel('ФИО *').fill(name);
    const createResponse = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith(`/universities/${universityId}/students`));
    await dialog.getByRole('button', { name: 'Сохранить' }).click();
    const created = await createResponse;
    expect(created.status()).toBe(201);
    studentId = ((await created.json()) as { id: string }).id;
    await expect(page.getByRole('table').getByText(name)).toBeVisible();
    await page.reload();
    await expect(page.getByRole('table').getByText(name)).toBeVisible();
    await page.getByRole('row').filter({ hasText: name }).getByRole('button', { name: 'Изменить' }).click();
    const edit = page.getByRole('dialog', { name: 'Редактировать студента' });
    await edit.getByLabel('ФИО *').fill(`${name} изменён`);
    await edit.getByLabel('Статус').selectOption('academic_leave');
    await edit.getByRole('button', { name: 'Сохранить' }).click();
    await expect(page.getByRole('table').getByText(`${name} изменён`)).toBeVisible();
    await page.reload();
    await expect(page.getByRole('table').getByText(`${name} изменён`)).toBeVisible();
    const detail = await request.get(`${apiBase}/api/v1/students/${studentId}`, { headers: { authorization } });
    expect(detail.ok()).toBeTruthy();
    expect(((await detail.json()) as { status: string }).status).toBe('academic_leave');
    await page.getByRole('row').filter({ hasText: `${name} изменён` }).getByRole('button', { name: 'Удалить' }).click();
    const deleteResponse = page.waitForResponse((response) => response.request().method() === 'DELETE' && response.url().endsWith(`/students/${studentId}`));
    await page.getByRole('dialog', { name: 'Удалить студента?' }).getByRole('button', { name: 'Удалить' }).click();
    expect((await deleteResponse).status()).toBe(204);
    await expect(page.getByRole('table').getByText(`${name} изменён`)).toHaveCount(0);
    studentId = '';
  } finally {
    if (studentId) await request.delete(`${apiBase}/api/v1/students/${studentId}`, { headers: { authorization } });
  }
});

for (const role of ['manager', 'user'] as const) {
  test(`demo ${role} cannot write an unassigned Passport`, async ({ page, request }) => {
    const authorization = await login(page, role, `${role}123`);
    const response = await request.post(`${apiBase}/api/v1/universities/${universityId}/meetings`, {
      headers: { authorization },
      data: { subject: `Denied ${Date.now()}`, meeting_at: new Date().toISOString(), meeting_type: 'online' },
    });
    expect(response.status()).toBe(role === 'manager' ? 404 : 403);
    await page.goto(`/universities/${universityId}?tab=meetings`);
    await expect(page.getByRole('button', { name: 'Добавить встречу' })).toHaveCount(0);
  });
}
