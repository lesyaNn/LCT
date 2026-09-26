import { expect, test, type Page } from '@playwright/test';
import { ApiRequestError, normalizeApiError } from '../shared/lib/api-errors';
import { currentUserFromDto, type CurrentUserDto } from '../shared/lib/current-user-repository';
import { getVisibleNavigationItems } from '../shared/config/navigation';

test('same-origin auth API reaches backend, not a Next.js 404 page', async ({ request }) => {
  const response = await request.get('/api/v1/auth/me');
  expect(response.status()).toBe(401);
  expect(response.headers()['content-type']).toContain('application/json');
});

test('Retry recovers admin access after a transient /auth/me error', async ({ page }) => {
  const account = credentials('admin');
  test.skip(!account, 'Set E2E_ADMIN_USERNAME and E2E_ADMIN_PASSWORD.');
  let attempts = 0;
  await page.route('**/api/v1/auth/me', async (route) => {
    attempts += 1;
    if (attempts === 1) {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ error: { code: 'ENTITY_NOT_FOUND', message: 'Test-only transient response' } }),
      });
    } else {
      await route.continue();
    }
  });
  await page.goto('/login');
  await page.locator('input[name="username"]').fill(account!.username);
  await page.locator('input[name="password"]').fill(account!.password);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await expect(page.getByRole('heading', { name: 'Не удалось проверить доступ' })).toBeVisible();
  await page.getByRole('button', { name: 'Повторить' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('button', { name: /Администрирование/ })).toBeVisible();
  expect(attempts).toBe(2);
});

test.describe('auth foundation adapters', () => {
  test('adapts backend MeOut and Keycloak assignment scope once', () => {
    const dto: CurrentUserDto = {
      id: 'subject-1',
      username: 'manager',
      email: 'manager@example.test',
      name: 'Мария Менеджерова',
      roles: ['manager'],
      permissions: ['workflow.read', 'audit.read', 'workflow.read'],
    };

    const user = currentUserFromDto(dto, [
      '11111111-1111-4111-8111-111111111111',
      'not-a-uuid',
      '11111111-1111-4111-8111-111111111111',
    ]);

    expect(user).toMatchObject({
      id: 'subject-1',
      role: 'manager',
      roleLabel: 'Руководитель',
      permissions: ['audit.read', 'workflow.read'],
      scope: { kind: 'group', universityIds: ['11111111-1111-4111-8111-111111111111'] },
      authSource: 'keycloak',
    });
  });

  test('maps canonical backend field errors without exposing the raw envelope', () => {
    const normalized = normalizeApiError(new ApiRequestError(422, {
      error: {
        code: 'VALIDATION_ERROR',
        message: 'Проверьте правильность заполнения полей.',
        request_id: '00000000-0000-4000-8000-000000000000',
        details: {
          field_errors: [{
            field: 'program_id',
            message: 'Программа не закреплена за указанным вузом.',
            type: 'value_error.program_university_mismatch',
          }],
        },
      },
    }));

    expect(normalized).toMatchObject({
      kind: 'validation',
      status: 422,
      code: 'VALIDATION_ERROR',
      message: 'Исправьте ошибки в форме.',
      details: {},
      fieldErrors: [{
        field: 'program_id',
        message: 'Программа не закреплена за указанным вузом.',
        code: 'VALUE_ERROR.PROGRAM_UNIVERSITY_MISMATCH',
      }],
    });
  });

  test('drives navigation from backend permissions', () => {
    const user = currentUserFromDto({
      id: 'subject-2',
      username: 'user',
      email: null,
      name: null,
      roles: ['user'],
      permissions: ['university.read', 'workflow.read'],
    }, []);

    expect(getVisibleNavigationItems(user).map((item) => item.href)).toEqual([
      '/universities',
      '/workflows',
      '/docs',
    ]);
  });
});

type RuntimeRole = 'admin' | 'manager' | 'user';

function credentials(role: RuntimeRole): { username: string; password: string } | null {
  const prefix = `E2E_${role.toUpperCase()}`;
  const username = process.env[`${prefix}_USERNAME`]?.trim();
  const password = process.env[`${prefix}_PASSWORD`]?.trim();
  return username && password ? { username, password } : null;
}

async function login(page: Page, role: RuntimeRole, username: string, password: string) {
  await page.goto('/login');
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  const meResponsePromise = page.waitForResponse((response) => (
    response.request().method() === 'GET' && new URL(response.url()).pathname === '/api/v1/auth/me'
  ));
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const meResponse = await meResponsePromise;
  await page.waitForURL((url) => url.pathname === '/dashboard');

  expect(meResponse.status()).toBe(200);
  const authorization = meResponse.request().headers().authorization;
  expect(authorization).toMatch(/^Bearer\s+\S+$/);
  const me = await meResponse.json() as CurrentUserDto;
  expect(me.username).toBe(username);
  expect(me.roles).toContain(role);
  expect(Array.isArray(me.permissions)).toBeTruthy();
  const tokenPayload = JSON.parse(Buffer.from(authorization.replace(/^Bearer\s+/, '').split('.')[1], 'base64url').toString('utf8')) as Record<string, unknown>;
  const rawScope = tokenPayload.university_ids ?? tokenPayload.university_id;
  const universityIds = typeof rawScope === 'string'
    ? [rawScope]
    : Array.isArray(rawScope) ? rawScope.filter((value): value is string => typeof value === 'string') : [];
  const user = currentUserFromDto(me, universityIds);
  return { authorization, me, user, apiOrigin: new URL(meResponse.url()).origin };
}

for (const role of ['admin', 'manager', 'user'] as const) {
  test(`real Keycloak + /auth/me for ${role}`, async ({ page }) => {
    const account = credentials(role);
    test.skip(!account, `Set E2E_${role.toUpperCase()}_USERNAME and E2E_${role.toUpperCase()}_PASSWORD.`);
    if (!account) return;

    const { authorization, me, user, apiOrigin } = await login(page, role, account.username, account.password);
    const displayName = me.name || me.username || 'Пользователь';
    await expect(page.getByText(displayName, { exact: true }).first()).toBeVisible();
    expect(user.scope.kind).toBe(role === 'admin' ? 'all' : role === 'manager' ? 'group' : 'own');

    if (role === 'admin') {
      await expect(page.getByRole('button', { name: /Администрирование/ })).toBeVisible();
      await page.getByRole('button', { name: /Администрирование/ }).click();
      await expect(page.getByRole('link', { name: 'Пользователи и права' })).toBeVisible();
    } else {
      await expect(page.getByRole('link', { name: 'Пользователи и права' })).toHaveCount(0);
    }

    if (role === 'user') {
      await expect(page.getByRole('button', { name: /Администрирование/ })).toHaveCount(0);
    } else if (role === 'manager') {
      const forbiddenStatus = await page.evaluate(async ({ header, origin }) => {
        const response = await fetch(`${origin}/api/v1/auth/test/admin`, { headers: { Authorization: header } });
        return response.status;
      }, { header: authorization, origin: apiOrigin });
      expect(forbiddenStatus).toBe(403);
      await expect(page).toHaveURL(/\/dashboard$/);
      await expect(page.getByText(displayName, { exact: true }).first()).toBeVisible();
    }

    await page.getByRole('button', { name: new RegExp(displayName) }).click();
    await page.getByRole('menuitem', { name: 'Выйти' }).click();
    await expect(page.locator('input[name="username"]')).toBeVisible();
  });
}
