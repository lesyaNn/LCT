import { expect, test } from '@playwright/test';

test('isolated backend mock adapter: Passport, Workflow idempotency and unavailable isolation', async ({ page, request }) => {
  test.skip(process.env.E2E_STAGE11_ISOLATED !== '1', 'Run only against the disposable Stage 11 realm and DB.');
  const api = `${process.env.E2E_API_URL ?? 'http://localhost:28000'}/api/v1`;
  await page.goto('/login');
  await page.locator('input[name="username"]').fill(process.env.E2E_STAGE11_ADMIN_USERNAME ?? 'admin');
  await page.locator('input[name="password"]').fill(process.env.E2E_STAGE11_ADMIN_PASSWORD ?? 'admin123');
  const meResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const auth = (await meResponse).request().headers().authorization;
  expect(auth).toMatch(/^Bearer\s+\S+$/);
  const headers = { authorization: auth };
  const stamp = Date.now();
  const post = async (path: string, data: Record<string, unknown>) => {
    const response = await request.post(`${api}${path}`, { headers, data });
    expect(response.status(), `${path}: ${await response.text()}`).toBe(201);
    return response.json() as Promise<Record<string, unknown>>;
  };
  const university = await post('/universities', { name: `Stage11 E2E ${stamp}`, city: 'Москва' });
  const direction = await post('/directions', { code: `e2e-${stamp}`, name: `Stage11 direction ${stamp}` });
  const program = await post('/programs', { direction_id: direction.id, name: `Stage11 program ${stamp}` });
  await post(`/universities/${university.id}/programs`, { program_id: program.id });
  const templatesResponse = await request.get(`${api}/workflow/templates`, { headers });
  expect(templatesResponse.status()).toBe(200);
  const activeTemplates = ((await templatesResponse.json()).items as Array<{ id: string; is_active: boolean }>).filter((item) => item.is_active);
  if (activeTemplates.length === 0) {
    const template = await post('/workflow/templates', { name: `Stage11 template ${stamp}`, is_active: true });
    await post(`/workflow/templates/${template.id}/stages`, { name: 'Инициация', order_index: 1 });
  } else {
    expect(activeTemplates).toHaveLength(1);
  }
  for (const source of ['lms', 'website']) {
    const sync = await request.post(`${api}/integrations/sync`, { headers, data: { university_id: university.id, source } });
    expect(sync.status(), await sync.text()).toBe(200);
    expect((await sync.json()).mode).toBe('mock');
  }
  const metricsResponse = await request.get(`${api}/integrations/metrics`, { headers });
  expect(metricsResponse.status()).toBe(200);
  const metrics = await metricsResponse.json() as { lms_students: number; website_applications_7d: number };
  expect(metrics.lms_students).toBeGreaterThanOrEqual(1);
  expect(metrics.website_applications_7d).toBeGreaterThanOrEqual(1);
  await page.goto('/dashboard');
  await expect(page.getByRole('link', { name: 'Открыть список ВУЗов с заявками с сайта' })).not.toContainText('—');
  await expect(page.getByRole('link', { name: 'Открыть список ВУЗов с данными LMS' })).not.toContainText('—');
  await page.getByRole('link', { name: 'Открыть список ВУЗов с данными LMS' }).click();
  await expect(page).toHaveURL(/external_source=lms/);
  await expect(page.getByRole('button', { name: /Удалить фильтр «Источник: LMS»/ })).toBeVisible();
  await expect(page.getByRole('link', { name: `Stage11 E2E ${stamp}` })).toBeVisible();

  await page.goto(`/universities/${university.id}?tab=students`);
  await expect(page.getByText('Тестовый обучающийся').first()).toBeVisible();
  await expect(page.getByTestId('external-badge')).toContainText('тест');
  await expect(page.getByTestId('sync-date').first()).not.toContainText('недоступно');

  await page.goto(`/universities/${university.id}?tab=programs`);
  await expect(page.getByText(`Stage11 program ${stamp}`).first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Создать Workflow' }).first()).toBeVisible();
  const createResponse = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/workflow/instances/from-external' && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Создать Workflow' }).first().click();
  const created = await createResponse;
  expect(created.status()).toBe(200);
  const result = await created.json() as { instance_id: string; existing: boolean };
  expect(result.existing).toBe(false);
  await page.goto(`/universities/${university.id}?tab=programs`);
  await expect(page.getByRole('button', { name: 'Перейти в Workflow' }).first()).toBeVisible();
  const repeat = await request.post(`${api}/workflow/instances/from-external`, { headers, data: {
    university_id: university.id, source: 'website', external_id: `mock-website:${university.id}:${program.id}`,
  } });
  expect(repeat.status()).toBe(200);
  expect((await repeat.json()).instance_id).toBe(result.instance_id);
  const instances = await request.get(`${api}/workflow/instances?university_id=${university.id}`, { headers });
  expect((await instances.json()).total).toBe(1);

  await page.route((url) => url.pathname === `/api/v1/universities/${university.id}/external-data`
    && url.searchParams.get('source') === 'lms', (route) => route.fulfill({
    status: 503, contentType: 'application/json',
    body: JSON.stringify({ error: { code: 'EXTERNAL_SOURCE_UNAVAILABLE', message: 'Внешний источник данных временно недоступен.' } }),
  }));
  await page.goto(`/universities/${university.id}?tab=students`);
  await expect(page.getByText('Тестовый обучающийся').first()).toBeVisible();
  await expect(page.getByRole('status').filter({ hasText: 'Источник LMS временно недоступен.' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Повторить' })).toBeVisible();
});
