import { expect, test, type Page } from '@playwright/test';

type Role = 'admin' | 'manager' | 'user';

function credentials(role: Role) {
  const prefix = `E2E_${role.toUpperCase()}`;
  const username = process.env[`${prefix}_USERNAME`]?.trim();
  const password = process.env[`${prefix}_PASSWORD`]?.trim();
  return username && password ? { username, password } : null;
}

async function login(page: Page, username: string, password: string): Promise<string> {
  await page.goto('/login');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  const meResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const response = await meResponse;
  expect(response.status()).toBe(200);
  await page.waitForURL((url) => url.pathname === '/dashboard');
  return response.request().headers().authorization ?? '';
}

for (const role of ['admin', 'manager', 'user'] as const) {
  test(`${role}: real Keycloak access to Admin Users`, async ({ page, request }) => {
    const account = credentials(role);
    test.skip(!account, `Set E2E_${role.toUpperCase()}_USERNAME and E2E_${role.toUpperCase()}_PASSWORD.`);
    const authorization = await login(page, account!.username, account!.password);
    expect(authorization).toMatch(/^Bearer\s+\S+$/);
    const apiUrl = `${process.env.E2E_API_URL ?? 'http://localhost:8000'}/api/v1/admin/users`;
    const apiResponse = await request.get(apiUrl, { headers: { authorization } });
    expect(apiResponse.status()).toBe(role === 'admin' ? 200 : 403);
    await page.goto('/admin/users');
    if (role === 'admin') {
      await expect(page.getByRole('heading', { name: 'Пользователи и права' })).toBeVisible();
      await expect(page.getByTestId('users-table')).toBeVisible();
      await expect(page.getByRole('button', { name: 'Пригласить пользователя' })).toBeEnabled();
      const target = process.env.E2E_ADMIN_TEST_USERNAME?.trim();
      if (target) {
        const filtered = await request.get(`${apiUrl}?search=${encodeURIComponent(target)}`, { headers: { authorization } });
        expect(filtered.status()).toBe(200);
        const account = ((await filtered.json()).items as Array<{ username: string; email: string }>).find((item) => item.username === target);
        expect(account).toBeTruthy();
        await page.getByPlaceholder('Найти пользователя').fill(target);
        const targetRow = page.getByRole('row').filter({ has: page.getByText(account!.email, { exact: true }) });
        await expect(targetRow).toBeVisible();
        await targetRow.getByRole('button', { name: 'Настроить' }).click();
        await expect(page.getByTestId('role-select')).toBeVisible();
        await expect(page.getByTestId('scope-multiselect')).toBeVisible();
        await page.getByTestId('block-button').click();
        await expect(page.getByRole('heading', { name: /Заблокировать пользователя\?|Разблокировать пользователя\?/ })).toBeVisible();
        await page.getByRole('button', { name: 'Отмена' }).click();
      }
    } else {
      await expect(page.getByText(/нет доступа|недостаточно прав|доступ запрещён/i).first()).toBeVisible();
      await expect(page.getByRole('button', { name: 'Пригласить пользователя' })).toHaveCount(0);
    }
  });
}

test('isolated realm: scope, block/unblock and invite use real APIs', async ({ page, request, browser }) => {
  test.skip(process.env.E2E_ADMIN_USERS_MUTATIONS !== '1' || process.env.E2E_ADMIN_USERS_ISOLATED !== '1',
    'Opt in only for a dedicated Keycloak realm and database.');
  const admin = credentials('admin');
  const user = credentials('user');
  test.skip(!admin || !user, 'Set dedicated admin and user credentials.');

  const authorization = await login(page, admin!.username, admin!.password);
  const api = `${process.env.E2E_API_URL ?? 'http://localhost:8000'}/api/v1`;
  const headers = { authorization };
  const stamp = Date.now();
  const universityNames = [`E2E University A ${stamp}`, `E2E University B ${stamp}`];
  const universities = [] as string[];
  for (const name of universityNames) {
    const created = await request.post(`${api}/universities`, { headers, data: { name } });
    expect(created.status()).toBe(201);
    universities.push((await created.json()).id as string);
  }

  const found = await request.get(`${api}/admin/users?search=${encodeURIComponent(user!.username)}`, { headers });
  expect(found.status()).toBe(200);
  const target = ((await found.json()).items as Array<{ id: string; username: string; email: string }>).find((item) => item.username === user!.username);
  expect(target).toBeTruthy();
  const unblockedFixture = await request.post(`${api}/admin/users/${target!.id}/block`, { headers, data: { blocked: false } });
  expect(unblockedFixture.status()).toBe(200);
  const resetTarget = await request.patch(`${api}/admin/users/${target!.id}`, { headers, data: {
    role: 'user', scope: { kind: 'universities', university_ids: universities },
  } });
  expect(resetTarget.status()).toBe(200);

  await page.goto('/admin/users');
  await page.getByPlaceholder('Найти пользователя').fill(user!.username);
  const row = page.getByRole('row').filter({ has: page.getByText(target!.email, { exact: true }) });
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: 'Настроить' }).click();
  const drawer = page.getByRole('dialog', { name: 'Настройки пользователя' });
  await expect(drawer.getByTestId('role-select')).toHaveValue('user');
  await drawer.getByTestId('role-select').selectOption('manager');
  await drawer.getByTestId('scope-multiselect').locator('summary').click();
  await drawer.getByTestId('scope-multiselect').getByRole('checkbox', { name: universityNames[1] }).uncheck();
  await drawer.getByTestId('scope-multiselect').locator('summary').click();
  await drawer.getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Данные пользователя сохранены')).toBeVisible();
  const detail = await request.get(`${api}/admin/users/${target!.id}`, { headers });
  expect(detail.status()).toBe(200);
  const updated = await detail.json();
  expect(updated.role).toBe('manager');
  expect(updated.scope.university_ids).toEqual([universities[0]]);

  const userContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' });
  try {
    const userPage = await userContext.newPage();
    const userAuthorization = await login(userPage, user!.username, user!.password);
    const userMe = await request.get(`${api}/auth/me`, { headers: { authorization: userAuthorization } });
    expect(userMe.status()).toBe(200);
    expect((await userMe.json()).roles).toContain('manager');
    const visible = await request.get(`${api}/universities?page=1&page_size=100`, { headers: { authorization: userAuthorization } });
    expect(visible.status()).toBe(200);
    expect(((await visible.json()).items as Array<{ id: string }>).map((item) => item.id)).toEqual([universities[0]]);
  } finally {
    await userContext.close();
  }

  await drawer.getByTestId('block-button').click();
  await page.getByRole('dialog', { name: 'Заблокировать пользователя?' }).getByRole('button', { name: 'Заблокировать' }).click();
  await expect(page.getByText('Пользователь заблокирован')).toBeVisible();
  expect((await (await request.get(`${api}/admin/users/${target!.id}`, { headers })).json()).status).toBe('blocked');
  const blockedContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' });
  try {
    const blockedPage = await blockedContext.newPage();
    await blockedPage.goto('/login');
    await blockedPage.locator('input[name="username"]').fill(user!.username);
    await blockedPage.locator('input[name="password"]').fill(user!.password);
    await blockedPage.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
    await expect(blockedPage.getByText(/заблокирована|Неверное имя пользователя|Неправильное имя пользователя/i)).toBeVisible();
  } finally {
    await blockedContext.close();
  }
  await drawer.getByTestId('block-button').click();
  await page.getByRole('dialog', { name: 'Разблокировать пользователя?' }).getByRole('button', { name: 'Разблокировать' }).click();
  await expect(page.getByText('Пользователь разблокирован')).toBeVisible();
  const unblockedContext = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000' });
  try {
    const unblockedPage = await unblockedContext.newPage();
    expect(await login(unblockedPage, user!.username, user!.password)).toMatch(/^Bearer\s+\S+$/);
  } finally {
    await unblockedContext.close();
  }

  await drawer.getByRole('button', { name: 'Закрыть' }).click();
  await page.getByRole('button', { name: 'Пригласить пользователя' }).click();
  const invite = page.getByRole('dialog', { name: 'Пригласить пользователя' });
  const invitedUsername = `e2e.user.${stamp}`;
  await invite.getByPlaceholder('Например, Ольга Соколова').fill('E2E Пользователь');
  await invite.getByPlaceholder('olga.sokolova').fill(invitedUsername);
  await invite.getByPlaceholder('olga@example.ru').fill(`${invitedUsername}@example.test`);
  await invite.getByRole('button', { name: 'Создать приглашение' }).click();
  await expect(page.getByText('Учётная запись создана')).toBeVisible();
  await expect(page.getByText('Письмо не отправлено: проверьте настройку почты Keycloak.')).toBeVisible();
  const invited = await request.get(`${api}/admin/users?search=${invitedUsername}`, { headers });
  expect(invited.status()).toBe(200);
  expect((await invited.json()).total).toBe(1);
  const duplicate = await request.post(`${api}/admin/users/invite`, { headers, data: {
    name: 'E2E Пользователь', username: invitedUsername, email: `${invitedUsername}@example.test`,
    role: 'user', scope: { kind: 'universities', university_ids: [] },
  } });
  expect(duplicate.status()).toBe(409);

  await page.getByPlaceholder('Найти пользователя').fill(invitedUsername);
  const invitedRow = page.getByRole('row').filter({ has: page.getByRole('button', { name: new RegExp(invitedUsername, 'i') }) });
  await invitedRow.getByRole('button', { name: 'Настроить' }).click();
  const invitedDrawer = page.getByRole('dialog', { name: 'Настройки пользователя' });
  await invitedDrawer.getByRole('button', { name: 'Сбросить пароль' }).click();
  await page.getByRole('dialog', { name: 'Сбросить пароль пользователя?' }).getByRole('button', { name: 'Отправить письмо' }).click();
  await expect(page.getByText('Сброс пароля недоступен')).toBeVisible();

  const restored = await request.patch(`${api}/admin/users/${target!.id}`, { headers, data: {
    role: 'user', scope: { kind: 'universities', university_ids: [] },
  } });
  expect(restored.status()).toBe(200);
});
