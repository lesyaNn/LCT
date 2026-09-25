import { expect, test, type Page } from '@playwright/test';
import { serializeUniversityListQuery } from '../shared/lib/real-api-adapter';
import type { UniversityListQuery } from '../shared/lib/universities-repository';

type RuntimeRole = 'admin' | 'manager' | 'curator' | 'user';
type ApiPage<T> = { items: T[]; page: number; page_size: number; total: number };
type UniversityDto = {
  id: string;
  name: string;
  city: string | null;
  created_at: string;
  updated_at: string;
  health_score: number | null;
  health_status: 'green' | 'yellow' | 'red' | null;
};

function credentials(role: RuntimeRole): { username: string; password: string } | null {
  const prefix = `E2E_${role.toUpperCase()}`;
  const username = process.env[`${prefix}_USERNAME`]?.trim();
  const password = process.env[`${prefix}_PASSWORD`]?.trim();
  return username && password ? { username, password } : null;
}

async function login(page: Page, role: RuntimeRole) {
  const account = credentials(role);
  test.skip(!account, `Set E2E_${role.toUpperCase()}_USERNAME and E2E_${role.toUpperCase()}_PASSWORD.`);
  if (!account) throw new Error(`Missing ${role} credentials`);

  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(account.username);
  await page.locator('input[name="password"]').fill(account.password);
  const mePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const meResponse = await mePromise;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  expect(meResponse.status()).toBe(200);
  const authorization = meResponse.request().headers().authorization;
  expect(authorization).toMatch(/^Bearer\s+\S+$/);
  const payload = JSON.parse(Buffer.from(authorization.replace(/^Bearer\s+/, '').split('.')[1], 'base64url').toString('utf8')) as Record<string, unknown>;
  const rawScope = payload.university_ids ?? payload.university_id;
  const universityIds = typeof rawScope === 'string'
    ? [rawScope]
    : Array.isArray(rawScope) ? rawScope.filter((value): value is string => typeof value === 'string') : [];
  return { authorization, universityIds, apiOrigin: new URL(meResponse.url()).origin, subject: String(payload.sub ?? '') };
}

async function apiGet<T>(page: Page, origin: string, authorization: string, path: string) {
  return page.evaluate(async ({ apiOrigin, header, apiPath }) => {
    const response = await fetch(`${apiOrigin}${apiPath}`, { headers: { Authorization: header } });
    return { status: response.status, body: await response.json().catch(() => null) };
  }, { apiOrigin: origin, header: authorization, apiPath: path }) as Promise<{ status: number; body: T }>;
}

test('serializes the canonical University query contract once', () => {
  const query: UniversityListQuery = {
    filters: {
      search: '  университет  ',
      city: 'Москва',
      universityIds: ['11111111-1111-4111-8111-111111111111'],
      programIds: ['22222222-2222-4222-8222-222222222222'],
      productIds: ['33333333-3333-4333-8333-333333333333'],
      responsibleIds: ['44444444-4444-4444-8444-444444444444'],
      healthStatuses: ['yellow'],
      workflowStageId: '',
      dateFrom: '2026-01-01',
      dateTo: '2026-12-31',
    },
    sort: 'health_score',
    order: 'desc',
    page: 2,
    pageSize: 20,
  };
  const params = serializeUniversityListQuery(query);
  expect(Object.fromEntries(params)).toMatchObject({
    page: '2', page_size: '20', search: 'университет', city: 'Москва',
    health_status: 'yellow', sort_by: 'health_score', sort_order: 'desc',
    date_from: '2026-01-01', date_to: '2026-12-31',
  });
  expect(params.getAll('university_ids')).toEqual(query.filters.universityIds);
  expect(params.getAll('program_ids')).toEqual(query.filters.programIds);
  expect(params.getAll('product_ids')).toEqual(query.filters.productIds);
  expect(params.getAll('responsible_ids')).toEqual(query.filters.responsibleIds);
  expect(params.has('workflowStageId')).toBeFalsy();
});

for (const role of ['admin', 'manager', 'curator', 'user'] as const) {
  test(`real University list obeys backend scope for ${role}`, async ({ page }) => {
    const auth = await login(page, role);
    const listResponsePromise = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === '/api/v1/universities' && url.searchParams.get('page_size') === '8';
    });
    await page.goto('/universities');
    const response = await listResponsePromise;
    expect(response.status()).toBe(200);
    const requestAuthorization = response.request().headers().authorization;
    expect(requestAuthorization).toMatch(/^Bearer\s+\S+$/);
    const requestPayload = JSON.parse(Buffer.from(requestAuthorization.replace(/^Bearer\s+/, '').split('.')[1], 'base64url').toString('utf8')) as Record<string, unknown>;
    expect(requestPayload.sub).toBe(auth.subject);
    const body = await response.json() as ApiPage<UniversityDto>;
    expect(body).toMatchObject({ page: 1, page_size: 8 });
    expect(Array.isArray(body.items)).toBeTruthy();
    expect(typeof body.total).toBe('number');

    if (role !== 'admin' && auth.universityIds.length) {
      expect(body.items.every((item) => auth.universityIds.includes(item.id))).toBeTruthy();
    } else if (role !== 'admin') {
      expect(body.total).toBe(0);
    }
  });
}

test('admin gets server filters, catalogs, stable caching and a real-id route', async ({ page }) => {
  const auth = await login(page, 'admin');
  const requestCounts = new Map<string, number>();
  page.on('request', (request) => {
    if (request.method() !== 'GET') return;
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/v1/')) return;
    requestCounts.set(`${url.pathname}?${url.searchParams}`, (requestCounts.get(`${url.pathname}?${url.searchParams}`) ?? 0) + 1);
  });

  const listPromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/universities' && url.searchParams.get('page_size') === '8';
  });
  await page.goto('/universities');
  const listResponse = await listPromise;
  const list = await listResponse.json() as ApiPage<UniversityDto>;
  await expect(page.getByRole('heading', { name: 'ВУЗы', level: 1 })).toBeVisible();
  const first = list.items[0];

  await expect.poll(() => requestCounts.get('/api/v1/universities?page=1&page_size=8&sort_by=name&sort_order=asc') ?? 0).toBe(1);
  await expect.poll(() => requestCounts.get('/api/v1/universities?page=1&page_size=100&sort_by=name&sort_order=asc') ?? 0).toBe(1);
  for (const path of ['products', 'directions', 'programs', 'vendors', 'responsibles']) {
    await expect.poll(() => requestCounts.get(`/api/v1/${path}?page=1&page_size=100`) ?? 0, path).toBe(1);
  }

  for (const path of ['products', 'directions', 'programs', 'vendors', 'responsibles']) {
    const response = await apiGet<ApiPage<unknown>>(page, auth.apiOrigin, auth.authorization, `/api/v1/${path}?page=1&page_size=100`);
    expect(response.status, path).toBe(200);
    expect(Array.isArray(response.body.items), path).toBeTruthy();
  }

  const searchTerm = first?.name.slice(0, 12) ?? '__definitely_missing_university__';
  const search = await apiGet<ApiPage<UniversityDto>>(page, auth.apiOrigin, auth.authorization, `/api/v1/universities?page=1&page_size=8&search=${encodeURIComponent(searchTerm)}`);
  expect(search.status).toBe(200);
  if (first) {
    expect(search.body.items.some((item) => item.id === first.id)).toBeTruthy();
    const exact = await apiGet<ApiPage<UniversityDto>>(page, auth.apiOrigin, auth.authorization, `/api/v1/universities?page=1&page_size=8&university_ids=${first.id}`);
    expect(exact.status).toBe(200);
    expect(exact.body.items.map((item) => item.id)).toEqual([first.id]);
  }
  const sorted = await apiGet<ApiPage<UniversityDto>>(page, auth.apiOrigin, auth.authorization, '/api/v1/universities?page=1&page_size=1&sort_by=health_score&sort_order=desc');
  expect(sorted.status).toBe(200);
  expect(sorted.body.page_size).toBe(1);
  const empty = await apiGet<ApiPage<UniversityDto>>(page, auth.apiOrigin, auth.authorization, '/api/v1/universities?page=1&page_size=8&search=__definitely_missing_university__');
  expect(empty.status).toBe(200);
  expect(empty.body.total).toBe(0);

  const catalogRequestsBeforeSearch = [...requestCounts.entries()].filter(([key]) => !key.startsWith('/api/v1/universities?')).reduce((sum, [, count]) => sum + count, 0);
  const uiSearchPromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/universities' && url.searchParams.get('page_size') === '8' && Boolean(url.searchParams.get('search'));
  });
  await page.getByLabel('Поиск по названию вуза').fill(searchTerm);
  expect((await uiSearchPromise).status()).toBe(200);
  const catalogRequestsAfterSearch = [...requestCounts.entries()].filter(([key]) => !key.startsWith('/api/v1/universities?')).reduce((sum, [, count]) => sum + count, 0);
  expect(catalogRequestsAfterSearch).toBe(catalogRequestsBeforeSearch);

  if (first) {
    await page.getByRole('link', { name: first.name, exact: true }).first().click();
    await page.waitForURL((url) => url.pathname === `/universities/${first.id}`);
    await expect(page.getByRole('heading', { name: first.name, level: 1 })).toBeVisible();
  }
});

test('University list exposes the shared error state and retry', async ({ page }) => {
  await login(page, 'admin');
  let failList = true;
  await page.route('**/api/v1/universities?**', async (route) => {
    const url = new URL(route.request().url());
    if (failList && url.searchParams.get('page_size') === '8') {
      await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'SERVICE_UNAVAILABLE' } }) });
      return;
    }
    await route.continue();
  });
  await page.goto('/universities');
  const retry = page.getByRole('button', { name: 'Повторить' }).last();
  await expect(retry).toBeVisible({ timeout: 20_000 });
  failList = false;
  await retry.click();
  await expect(page.getByRole('heading', { name: 'ВУЗы', level: 1 })).toBeVisible();
  await expect(page.getByText('Вузы пока не добавлены').or(page.locator('[data-testid^="university-row-"]').first())).toBeVisible();
});
