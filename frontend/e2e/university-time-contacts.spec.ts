import { expect, test, type Page } from '@playwright/test';

test.use({ launchOptions: process.env.E2E_CHROMIUM_PATH ? { executablePath: process.env.E2E_CHROMIUM_PATH } : {} });
const universityId = '7d0af272-c031-478a-83a4-5328c375ab43';
const person = { id: '6bd3499d-b7a1-4b71-a7c6-62418c8578dc', full_name: 'Анна Иванова', role: 'Куратор от вуза', email: 'anna@example.org', phone: '+7 (900) 123-45-67', is_primary: true };

async function session(page: Page, timeZone: string | null = 'Asia/Vladivostok', clipboardFails = false) {
  const mutations: string[] = [];
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(fails => {
    Object.assign(window, { copiedValues: [] });
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (text: string) => {
      if (fails) throw new DOMException('Permission denied', 'NotAllowedError');
      (window as unknown as { copiedValues: string[] }).copiedValues.push(text);
    } } });
  }, clipboardFails);
  await page.route('**/realms/rtk/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/3p-cookies/step1.html')) {
      await route.fulfill({ contentType: 'text/html', body: '<script>parent.postMessage("supported", "*")</script>' });
    } else if (url.pathname.endsWith('/auth')) {
      const redirect = new URL(url.searchParams.get('redirect_uri')!);
      redirect.hash = new URLSearchParams({ state: url.searchParams.get('state')!, session_state: 'test-session', code: url.searchParams.get('nonce')! }).toString();
      await route.fulfill({ status: 302, headers: { location: redirect.toString() } });
    } else if (url.pathname.endsWith('/token')) {
      const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
      const token = `${part({ alg: 'RS256' })}.${part({ sub: 'contact-test', nonce: new URLSearchParams(route.request().postData() ?? '').get('code'), exp: Math.floor(Date.now() / 1000) + 3600, iat: Math.floor(Date.now() / 1000), realm_access: { roles: ['user'] }, aud: 'rtk-api' })}.test-signature`;
      await route.fulfill({ contentType: 'application/json', headers: {
        'Access-Control-Allow-Origin': new URL(process.env.E2E_BASE_URL || 'http://localhost:3000').origin,
        'Access-Control-Allow-Credentials': 'true', 'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Methods': 'POST, OPTIONS',
      }, body: JSON.stringify({ access_token: token, id_token: token, refresh_token: token, token_type: 'Bearer', expires_in: 3600 }) });
    } else await route.abort();
  });
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') mutations.push(`${route.request().method()} ${path}`);
    let body: unknown = { items: [], total: 0, page: 1, page_size: 20 };
    if (path.endsWith('/auth/me')) body = { id: 'contact-test', username: 'reader', name: 'Тест', roles: ['user'], permissions: ['university.read', 'catalog.read', 'assistant.use'] };
    if (path.endsWith('/passport')) body = {
      university: { id: universityId, name: 'Тестовый университет', city: timeZone ? 'Владивосток' : 'Неизвестный город', time_zone: timeZone },
      programs: [], products: [], licenses: [], contracts: [], documents: [], meetings: [], responsibles: [person], last_interactions: [],
      workflow_summary: { instance_id: null, current_stage: null, progress_percent: 0, overdue_stages: 0, next_due_date: null },
    };
    if (path.endsWith('/contracts')) body = { items: [{ id: 'contract-1', contract_number: 'ДГ-2026/001', signed_at: '2026-10-01', expires_at: null, status: 'active', status_raw: 'signed', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', university_id: universityId }], page: 1, page_size: 20, total: 1 };
    if (path.endsWith('/unread-count')) body = { count: 0 };
    if (path.endsWith('/assistant/status')) body = { enabled: false, ready: false, reason: 'disabled' };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return { mutations, errors };
}

async function copied(page: Page) {
  return page.evaluate(() => (window as unknown as { copiedValues: string[] }).copiedValues);
}

test('reader sees university clock, copies contact methods and contract number', async ({ page }, testInfo) => {
  const checks = await session(page);
  await page.clock.install({ time: new Date('2026-10-17T16:30:00Z') });
  await page.goto(`/universities/${universityId}?tab=responsibles`);
  const clocks = page.getByRole('group', { name: 'Местное время вуза' });
  await expect(clocks).toHaveCount(1);
  await expect(clocks).toContainText('18.10.2026');
  await expect(clocks).toContainText('UTC+10');
  await expect(clocks.locator('time')).toHaveText(/^02:30:\d{2}$/);
  const firstTime = await clocks.locator('time').textContent();
  await page.clock.fastForward(2000);
  await expect(clocks.locator('time')).not.toHaveText(firstTime!);
  await expect(clocks).toContainText('Вне рабочего времени');
  await expect(clocks).toContainText('Ориентир: 09:00–18:00');
  await expect(page.getByRole('button', { name: 'Добавить ответственного' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Копировать контакт: Анна Иванова' })).toHaveCount(0);
  await page.getByRole('link', { name: person.phone }).hover();
  await page.getByRole('button', { name: 'Копировать телефон: Анна Иванова' }).click();
  await page.getByRole('link', { name: person.email }).hover();
  await page.getByRole('button', { name: 'Копировать email: Анна Иванова' }).click();
  await expect.poll(() => copied(page)).toEqual([person.phone, person.email]);
  await expect(page.getByRole('link', { name: person.email })).toHaveAttribute('href', 'mailto:anna@example.org');
  await expect(page.getByRole('link', { name: person.phone })).toHaveAttribute('href', 'tel:+79001234567');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('article').filter({ hasText: 'Анна Иванова' }).scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('link', { name: person.phone }).hover();
  await page.getByRole('button', { name: 'Копировать телефон: Анна Иванова' }).click();
  await expect.poll(() => copied(page)).toHaveLength(3);
  await page.screenshot({ path: testInfo.outputPath('contacts-mobile.png'), fullPage: true });
  await page.goto(`/universities/${universityId}?tab=documents`);
  await page.getByText('ДГ-2026/001', { exact: true }).hover();
  await page.getByRole('button', { name: 'Копировать номер договора ДГ-2026/001' }).click();
  await expect.poll(() => copied(page)).toEqual(['ДГ-2026/001']);
  expect(checks.mutations).toEqual([]);
  expect(checks.errors).toEqual([]);
});

test('unknown city is explicit and clipboard refusal has an actionable error', async ({ page }) => {
  const checks = await session(page, null, true);
  await page.goto(`/universities/${universityId}?tab=responsibles`);
  await expect(page.getByText('Местное время не определено')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Местное время вуза' })).toHaveCount(0);
  await page.getByRole('link', { name: person.phone }).hover();
  await page.getByRole('button', { name: 'Копировать телефон: Анна Иванова' }).click();
  const error = page.getByRole('alert').filter({ hasText: 'Не удалось скопировать' });
  await expect(error).toBeVisible();
  await expect(error).toContainText('HTTPS');
  await expect(page.getByText('Скопировано', { exact: true })).toHaveCount(0);
  expect(await copied(page)).toEqual([]);
  expect(checks.errors).toEqual([]);
});
