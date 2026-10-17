import { expect, test, type Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import type { OpenApiDocument, ServiceApiCatalog } from '../shared/lib/service-api';

test.use({ launchOptions: process.env.E2E_CHROMIUM_PATH ? { executablePath: process.env.E2E_CHROMIUM_PATH } : {} });

// Isolated browser contract test. OIDC and API responses are fixtures; no CRM mutations.
const catalog: ServiceApiCatalog = {
  version: '1.0.0', base_path: '/api/v1', openapi_path: '/api/v1/openapi.json',
  operation_count: 2, role: 'manager',
  operations: [
    { operation_id: 'list_universities', method: 'GET', path: '/api/v1/universities',
      summary: 'Список вузов', tags: ['Universities'], required_permissions: ['university.read'],
      allowed_roles: ['admin', 'manager', 'user'], role_allowed: true, deprecated: false },
    { operation_id: 'create_university', method: 'POST', path: '/api/v1/universities',
      summary: 'Создать вуз', tags: ['Universities'], required_permissions: ['catalog.manage'],
      allowed_roles: ['admin'], role_allowed: false, deprecated: false },
  ],
  limits: { heavy_requests_per_minute: 120, heavy_paths: ['/api/v1/analytics/overview'],
    assistant_requests_per_minute: 10, assistant_timeout_seconds: 120, max_upload_mb: 50 },
  errors: [{ code: 'CONFLICT', status: 409, message: 'Конфликт данных.' }],
};
const schema: OpenApiDocument = {
  openapi: '3.1.0', info: { title: 'CRM API', version: '1.0.0' },
  paths: { '/api/v1/universities': {
    get: { description: 'Возвращает доступные вузы.', parameters: [{ name: 'page', in: 'query', schema: { type: 'integer', default: 1 } }], responses: { '200': { description: 'Страница вузов' } } },
    post: { description: 'Создаёт вуз.', requestBody: { required: true, content: {
      'application/json': { example: { name: 'Тестовый университет', city: 'Москва' },
        schema: { type: 'object', required: ['name'], properties: { name: { type: 'string', minLength: 1 }, city: { anyOf: [{ type: 'string' }, { type: 'null' }] } } } },
    } }, responses: { '201': { description: 'Вуз создан' }, '204': { description: 'Без тела' } } },
  } },
};

async function mockSession(page: Page, failFirst = false, contract?: { catalog: ServiceApiCatalog; schema: OpenApiDocument }) {
  let nonce = '';
  let attempts = 0;
  const mutations: string[] = [];
  await page.route('**/realms/rtk/**', async route => {
    const url = new URL(route.request().url());
    const origin = new URL(process.env.E2E_BASE_URL || 'http://localhost:3000').origin;
    if (url.pathname.endsWith('/3p-cookies/step1.html')) {
      await route.fulfill({ contentType: 'text/html', body: '<script>parent.postMessage("supported", "*")</script>' });
    } else if (url.pathname.endsWith('/auth')) {
      nonce = url.searchParams.get('nonce') ?? '';
      const redirect = new URL(url.searchParams.get('redirect_uri')!);
      redirect.hash = new URLSearchParams({ state: url.searchParams.get('state')!, session_state: 'test-session', code: nonce }).toString();
      await route.fulfill({ status: 302, headers: { location: redirect.toString() } });
    } else if (url.pathname.endsWith('/token')) {
      const tokenNonce = new URLSearchParams(route.request().postData() ?? '').get('code') ?? nonce;
      const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
      const token = `${part({ alg: 'RS256' })}.${part({ sub: 'api-docs-browser-test', nonce: tokenNonce,
        exp: Math.floor(Date.now() / 1000) + 1800, iat: Math.floor(Date.now() / 1000),
        realm_access: { roles: ['manager'] }, aud: 'rtk-api',
      })}.test-signature`;
      await route.fulfill({ contentType: 'application/json', headers: {
        'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Methods': 'POST, OPTIONS',
      },
        body: JSON.stringify({ access_token: token, id_token: token, refresh_token: token, token_type: 'Bearer', expires_in: 1800 }) });
    } else {
      await route.abort();
    }
  });
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (request.method() !== 'GET') mutations.push(`${request.method()} ${pathname}`);
    let body: unknown = {};
    if (pathname === '/api/v1/auth/me') body = { id: 'api-docs-browser-test', username: 'manager', name: 'API Test', email: 'test@example.org', roles: ['manager'], permissions: ['university.read', 'university.edit'] };
    if (pathname === '/api/v1/service-api') {
      attempts += 1;
      if (failFirst && attempts === 1) {
        await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
        return;
      }
      body = contract?.catalog ?? catalog;
    }
    if (pathname === '/api/v1/openapi.json') body = contract?.schema ?? schema;
    if (pathname === '/api/v1/notifications/unread-count') body = { count: 0 };
    if (pathname === '/api/v1/assistant/conversations') body = { items: [], total: 0, page: 1, page_size: 1 };
    if (pathname === '/api/v1/assistant/status') body = { enabled: false, ready: false, reason: 'disabled', model: 'qwen3:1.7b', retrieval_mode: 'lexical', document_count: 0, knowledge_version: null };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return mutations;
}

test('API guide, live method viewer, schema download and read-only navigation', async ({ page }, testInfo) => {
  const mutations = await mockSession(page);
  await page.goto('/api', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await expect(page.getByRole('heading', { name: 'API', exact: true, level: 1 })).toBeVisible();
  await expect(page.getByRole('link', { name: 'API', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Создание вуза', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Скачать OpenAPI' })).toBeEnabled();
  await page.getByRole('tab', { name: 'Все методы' }).click();
  await expect(page.getByText('Найдено методов: 2')).toBeVisible();
  await page.getByLabel('Только разрешённые моей роли').check();
  await expect(page.getByText('Найдено методов: 1')).toBeVisible();
  await page.getByLabel('Только разрешённые моей роли').uncheck();
  await page.getByLabel('Метод', { exact: true }).selectOption('POST');
  await page.getByRole('button', { name: /POST.*Создать вуз/ }).click();
  await expect(page.getByRole('heading', { name: 'Тело запроса (обязательно)' })).toBeVisible();
  await expect(page.getByText('catalog.manage', { exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'name', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('api-method-desktop.png'), fullPage: true });
  await page.getByRole('tab', { name: 'Ошибки и ограничения' }).click();
  await expect(page.getByRole('cell', { name: 'CONFLICT', exact: true })).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать OpenAPI' }).click();
  expect((await download).suggestedFilename()).toBe('crm-openapi.json');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('tab', { name: 'Подключение и примеры' }).click();
  await expect(page.getByRole('heading', { name: 'Создание вуза', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.getByRole('tabpanel').evaluate(element => element.getBoundingClientRect().right <= window.innerWidth)).toBe(true);
  expect(await page.getByRole('button', { name: 'Скачать OpenAPI' }).evaluate(element => element.getBoundingClientRect().right <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('api-guide-mobile.png') });
  expect(mutations).toEqual([]);
});

test('guide remains readable when API contract fails and Retry reloads it', async ({ page }) => {
  await mockSession(page, true);
  await page.goto('/api', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const error = page.getByRole('alert').filter({ hasText: 'Не удалось загрузить контракт API' });
  await expect(error).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Что можно делать' })).toBeVisible();
  await page.getByRole('button', { name: 'Повторить загрузку' }).click();
  await expect(page.getByRole('button', { name: 'Скачать OpenAPI' })).toBeEnabled();
  await expect(error).toHaveCount(0);
});

test('method viewer accepts the complete mounted backend contract', async ({ page }, testInfo) => {
  test.skip(!process.env.E2E_SERVICE_API_PYTHON, 'Set E2E_SERVICE_API_PYTHON to a backend Python environment.');
  const json = execFileSync(process.env.E2E_SERVICE_API_PYTHON!, ['-B', '-c', [
    'import json', 'from app.main import app',
    'from app.core.security import CurrentUser', 'from app.modules.service_api.service import catalog',
    'print(json.dumps({"catalog":catalog(app,CurrentUser(id="browser-contract",roles={"manager"})).model_dump(),"schema":app.openapi()},ensure_ascii=False))',
  ].join(';')], { cwd: path.resolve(process.cwd(), '../backend'), encoding: 'utf8',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' }, maxBuffer: 4 * 1024 * 1024 });
  const contract: { catalog: ServiceApiCatalog; schema: OpenApiDocument } = JSON.parse(json);
  const mutations = await mockSession(page, false, contract);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/api', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.getByRole('tab', { name: 'Все методы' }).click();
  await expect(page.getByText(`Найдено методов: ${contract.catalog.operation_count}`)).toBeVisible();
  await page.getByLabel('Метод', { exact: true }).selectOption('POST');
  await page.getByLabel('Поиск методов').fill('/contracts');
  const create = contract.catalog.operations.find(operation => operation.path === '/api/v1/contracts' && operation.method === 'POST')!;
  await page.locator(`[aria-controls="operation-${create.operation_id}"]`).click();
  await expect(page.getByRole('cell', { name: 'contract_number', exact: true })).toBeVisible();
  await page.getByText('HTTP 201:', { exact: false }).click();
  await expect(page.getByRole('cell', { name: 'license_count', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('api-contract-desktop.png'), fullPage: true });
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});
