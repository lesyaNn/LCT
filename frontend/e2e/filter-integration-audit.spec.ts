import { expect, test } from '@playwright/test';

type PageResult<T> = { items: T[]; total: number };
type University = { id: string; name: string };
type Program = { name: string; status: 'planned' | 'active' | 'launched' | 'archived' };
type Teacher = { full_name: string; readiness: 'ready' | 'attention' | 'expired' };

test('program and teacher filters reach the API before pagination', async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  const me = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const authorization = (await me).request().headers().authorization;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  expect(authorization).toMatch(/^Bearer\s+\S+$/);
  const get = async <T,>(path: string) => {
    const response = await request.get(`http://localhost:3000/api/v1${path}`, { headers: { authorization } });
    expect(response.status(), `${path}: ${await response.text()}`).toBe(200);
    return response.json() as Promise<PageResult<T>>;
  };
  const universities = await get<University>('/universities?page=1&page_size=100');
  const candidate = await Promise.all(universities.items.map(async (university) => ({
    university,
    programs: await get<Program>(`/universities/${university.id}/passport/programs?page=1&page_size=100`),
    teachers: await get<Teacher>(`/universities/${university.id}/passport/teachers?page=1&page_size=100`),
  })));
  const fixture = candidate.find((item) => item.programs.items.length && item.teachers.items.length);
  test.skip(!fixture, 'A university with programs and teachers is required.');
  if (!fixture) return;

  const { id } = fixture.university;
  const status = fixture.programs.items[0].status;
  await page.goto(`/universities/${id}?tab=programs`);
  const programsSection = page.locator('section[aria-label="Программы"]').last();
  await expect(programsSection.getByRole('combobox', { name: 'Статус' })).toBeVisible();
  let releasePrograms: () => void = () => {};
  const programsGate = new Promise<void>((resolve) => { releasePrograms = resolve; });
  await page.route((url) => url.pathname === `/api/v1/universities/${id}/passport/programs` && url.searchParams.get('status') === status,
    async (route) => { await programsGate; await route.continue(); });
  const programResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === `/api/v1/universities/${id}/passport/programs` && url.searchParams.get('status') === status;
  });
  await programsSection.getByRole('combobox', { name: 'Статус' }).selectOption(status);
  await expect(page).toHaveURL(new RegExp(`program_status=${status}`));
  await expect(programsSection.getByText(fixture.programs.items[0].name).first()).toBeVisible();
  releasePrograms();
  const filteredPrograms = await programResponse;
  expect(filteredPrograms.status()).toBe(200);
  const programBody = await filteredPrograms.json() as PageResult<Program>;
  expect(programBody.total).toBe(fixture.programs.items.filter((item) => item.status === status).length);
  expect(programBody.items.every((item) => item.status === status)).toBeTruthy();
  await programsSection.getByRole('button', { name: 'Сбросить' }).click();
  await expect(programsSection.getByRole('combobox', { name: 'Статус' })).toHaveValue('all');
  await expect(page).not.toHaveURL(/program_status=/);

  const readiness = fixture.teachers.items[0].readiness;
  await page.goto(`/universities/${id}?tab=teachers`);
  const teachersSection = page.locator('section[aria-label="Преподаватели"]').last();
  await expect(teachersSection.getByRole('combobox', { name: 'Готовность' })).toBeVisible();
  let releaseTeachers: () => void = () => {};
  const teachersGate = new Promise<void>((resolve) => { releaseTeachers = resolve; });
  await page.route((url) => url.pathname === `/api/v1/universities/${id}/passport/teachers` && url.searchParams.get('readiness') === readiness,
    async (route) => { await teachersGate; await route.continue(); });
  const teacherResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === `/api/v1/universities/${id}/passport/teachers` && url.searchParams.get('readiness') === readiness;
  });
  await teachersSection.getByRole('combobox', { name: 'Готовность' }).selectOption(readiness);
  await expect(page).toHaveURL(new RegExp(`teacher_readiness=${readiness}`));
  await expect(teachersSection.getByText(fixture.teachers.items[0].full_name).first()).toBeVisible();
  releaseTeachers();
  const filteredTeachers = await teacherResponse;
  expect(filteredTeachers.status()).toBe(200);
  const teacherBody = await filteredTeachers.json() as PageResult<Teacher>;
  expect(teacherBody.total).toBe(fixture.teachers.items.filter((item) => item.readiness === readiness).length);
  expect(teacherBody.items.every((item) => item.readiness === readiness)).toBeTruthy();
  await teachersSection.getByRole('button', { name: 'Сбросить' }).click();
  await expect(teachersSection.getByRole('combobox', { name: 'Готовность' })).toHaveValue('all');
  await expect(page).not.toHaveURL(/teacher_readiness=/);
});

test('desktop dashboard presets occupy one row', async ({ page }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  const buttons = page.getByRole('group', { name: 'Период' }).first().getByRole('button');
  await expect(buttons).toHaveCount(4);
  const tops = await buttons.evaluateAll((elements) => elements.map((element) => Math.round(element.getBoundingClientRect().top)));
  expect(new Set(tops).size).toBe(1);
  for (const label of ['Текущий месяц', 'Текущий квартал', 'Текущий год', 'Прошлый год']) {
    const filtered = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === '/api/v1/analytics/overview' && url.searchParams.has('date_from') && url.searchParams.has('date_to');
    });
    await buttons.filter({ hasText: label }).click();
    await expect(page.getByTestId('dashboard-kpi')).toBeVisible();
    expect((await filtered).status()).toBe(200);
  }
});

test('filter surfaces stay inside the viewport on desktop, tablet and mobile', async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  const me = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const authorization = (await me).request().headers().authorization;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  const response = await request.get('http://localhost:3000/api/v1/universities?page=1&page_size=1', { headers: { authorization } });
  expect(response.ok()).toBeTruthy();
  const university = ((await response.json()) as PageResult<University>).items[0];
  const paths = ['/dashboard', '/universities', '/audit'];
  if (university) paths.push(`/universities/${university.id}?tab=programs`, `/universities/${university.id}?tab=teachers`);
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    for (const path of paths) {
      await page.goto(path);
      await expect(page.locator('main')).toBeVisible();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth), { message: `${path} overflows at ${width}` }).toBeLessThanOrEqual(width + 1);
    }
  }
  await page.setViewportSize({ width: 390, height: 900 });
  for (const path of ['/dashboard', '/universities', '/audit']) {
    await page.goto(path);
    await page.getByRole('button', { name: /^Фильтры/ }).first().click();
    await expect(page.getByRole('dialog', { name: 'Фильтры' })).toBeVisible();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth), { message: `${path} drawer overflows` }).toBeLessThanOrEqual(391);
    await page.getByRole('dialog', { name: 'Фильтры' }).getByRole('button', { name: 'Закрыть' }).click();
  }
});

test('audit period and available select filters reach server params', async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  const me = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const authorization = (await me).request().headers().authorization;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  const optionsResponse = await request.get('http://localhost:3000/api/v1/audit/filter-options', { headers: { authorization } });
  expect(optionsResponse.ok()).toBeTruthy();
  const options = await optionsResponse.json() as Record<string, unknown[]>;
  await page.goto('/audit');
  const surface = page.locator('section[aria-label="Фильтры журнала аудита"]');
  await expect(surface).toBeVisible();
  const periodResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/audit/events' && url.searchParams.get('date_from') === '2026-01-01';
  });
  await surface.getByLabel('От').fill('2026-01-01');
  expect((await periodResponse).status()).toBe(200);
  await surface.getByRole('button', { name: 'Сбросить' }).click();
  await expect(page).not.toHaveURL(/date_from=/);

  let testedSelects = 0;
  for (const [label, optionKey, queryKey] of [
    ['Пользователь', 'users', 'user_id'],
    ['ВУЗ', 'universities', 'university_id'],
    ['Тип действия', 'actions', 'action'],
    ['Тип сущности', 'entity_types', 'entity_type'],
  ]) {
    if (!options[optionKey]?.length) continue;
    testedSelects += 1;
    const details = surface.locator('details').filter({ has: page.locator('summary strong', { hasText: label }) }).first();
    await details.locator('summary').click();
    const apiResponse = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === '/api/v1/audit/events' && url.searchParams.has(queryKey);
    });
    await details.locator('input[type="checkbox"]').first().click();
    expect((await apiResponse).status()).toBe(200);
    await details.locator('summary').click();
    await surface.getByRole('button', { name: 'Сбросить' }).click();
    await expect(page).not.toHaveURL(new RegExp(`${optionKey === 'users' ? 'user' : optionKey === 'universities' ? 'university' : queryKey}=`));
  }
  expect(testedSelects).toBeGreaterThan(0);
});

test('university list filters send supported parameters and reset', async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  const me = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const authorization = (await me).request().headers().authorization;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  const universitiesResponse = await request.get('http://localhost:3000/api/v1/universities?page=1&page_size=1', { headers: { authorization } });
  expect(universitiesResponse.ok()).toBeTruthy();
  const first = ((await universitiesResponse.json()) as PageResult<University>).items[0];
  test.skip(!first, 'A university fixture is required.');
  if (!first) return;
  await page.goto('/universities');
  const surface = page.locator('section[aria-label="Фильтры списка вузов"]').first();
  await expect(surface).toBeVisible();
  const reset = async () => {
    await surface.getByRole('button', { name: 'Сбросить' }).click();
    await expect(surface.getByRole('button', { name: 'Сбросить' })).toBeDisabled();
  };
  const expectParam = (key: string) => page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/v1/universities' && url.searchParams.has(key);
  });
  const searchResponse = expectParam('search');
  await surface.getByLabel('Поиск по названию вуза').fill(first.name.slice(0, 8));
  expect((await searchResponse).status()).toBe(200);
  await reset();

  for (const [label, key] of [
    ['Вуз', 'university_ids'], ['Программа', 'program_ids'], ['Продукт', 'product_ids'],
    ['Ответственный', 'responsible_ids'], ['Health Score', 'health_status'],
  ]) {
    const details = surface.locator('details').filter({ has: page.locator('summary strong', { hasText: new RegExp(`^${label}$`, 'i') }) }).first();
    await details.locator('summary').click();
    await expect(details.locator('input[type="checkbox"]').first()).toBeVisible();
    const filtered = expectParam(key);
    await details.locator('input[type="checkbox"]').first().click();
    expect((await filtered).status()).toBe(200);
    await details.locator('summary').click();
    await reset();
  }
  const city = surface.getByLabel('Город');
  const cityValue = await city.evaluate((element) => (element as HTMLSelectElement).options[1]?.value ?? '');
  if (cityValue) {
    const filtered = expectParam('city');
    await city.selectOption(cityValue);
    expect((await filtered).status()).toBe(200);
    await reset();
  }
  const period = surface.getByRole('group', { name: /Период/ });
  const dated = expectParam('date_from');
  await period.getByRole('button', { name: 'Текущий год' }).click();
  expect((await dated).status()).toBe(200);
  await reset();
  await expect(surface.getByLabel('Текущий этап')).toBeDisabled();
});

test('Programs distinguishes an unconfigured site, imported data and a source failure', async ({ page, request }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  const me = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/v1/auth/me');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  const authorization = (await me).request().headers().authorization;
  await page.waitForURL((url) => url.pathname === '/dashboard');
  const universitiesResponse = await request.get('http://localhost:3000/api/v1/universities?page=1&page_size=100', { headers: { authorization } });
  expect(universitiesResponse.ok()).toBeTruthy();
  const universities = (await universitiesResponse.json()) as PageResult<University>;
  let fixture: { university: University; program: Program & { id: string } } | undefined;
  for (const university of universities.items) {
    const response = await request.get(`http://localhost:3000/api/v1/universities/${university.id}/passport/programs?page=1&page_size=1`, { headers: { authorization } });
    const programs = (await response.json()) as PageResult<Program & { id: string }>;
    if (programs.items[0]) { fixture = { university, program: programs.items[0] }; break; }
  }
  test.skip(!fixture, 'A university with a program is required.');
  if (!fixture) return;
  const { university, program } = fixture;
  const path = `/universities/${university.id}?tab=programs`;
  await page.goto(path);
  const section = page.locator('section[aria-label="Программы"]').last();
  await expect(section.getByText(program.name).first()).toBeVisible();
  await expect(section.getByText('Данные сайта не подключены')).toBeVisible();

  const externalPath = `/api/v1/universities/${university.id}/external-data`;
  const matchesWebsite = (url: URL) => url.pathname === externalPath && url.searchParams.get('source') === 'website';
  await page.route(matchesWebsite, (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    university_id: university.id, source: 'website', mode: 'import', synced_at: '2026-09-26T00:00:00Z', students: [],
    applications: [{ id: 'import-1', university_id: university.id, program_id: program.id, program_name: program.name,
      applications_count: 2, demand_score: null, source: 'website', synced_at: '2026-09-26T00:00:00Z', workflow_instance_id: null }],
  }) }));
  await page.reload();
  await expect(section.getByText(program.name).first()).toBeVisible();
  await expect(section.getByText('Импорт').first()).toBeVisible();
  await page.unroute(matchesWebsite);

  await page.route(matchesWebsite, (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({
    error: { code: 'EXTERNAL_SOURCE_UNAVAILABLE', message: 'Источник временно недоступен.' },
  }) }));
  await page.reload();
  await expect(section.getByText(program.name).first()).toBeVisible();
  await expect(section.getByText('Данные сайта сейчас недоступны')).toBeVisible();
  await expect(section.getByRole('table')).toBeVisible();
});

test('report status polling updates its row without replacing the page', async ({ page }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');

  const createdAt = new Date().toISOString();
  const job = { id: 'qa-polling-job', name: 'Проверка обновления', format: 'xlsx', status: 'building', progress: 10, created_at: createdAt };
  let polls = 0;
  await page.route((url) => url.pathname === '/api/v1/reports', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [job], total: 1, page: 1, page_size: 100 }) }));
  await page.route((url) => url.pathname === `/api/v1/reports/${job.id}`, (route) => {
    polls += 1;
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...job, progress: 10 + polls * 10 }) });
  });
  await page.goto('/reports');
  const jobs = page.getByRole('region', { name: 'Задачи отчётов' });
  await expect(jobs.getByText(job.name).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Параметры отчёта' })).toBeVisible();
  await expect.poll(() => polls).toBeGreaterThanOrEqual(2);
  await expect(jobs.getByText(job.name).first()).toBeVisible();
  await expect(jobs.getByRole('table')).toBeVisible();
});

test('window focus refresh keeps the Audit table visible', async ({ page }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Set E2E admin credentials.');
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await page.goto('/audit');
  const table = page.getByRole('table').first();
  await expect(table).toBeVisible();
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  let refreshes = 0;
  await page.route((url) => url.pathname === '/api/v1/audit/events', async (route) => {
    refreshes += 1;
    await gate;
    await route.continue();
  });
  await page.waitForTimeout(31_000);
  const otherTab = await page.context().newPage();
  await otherTab.goto('about:blank');
  await otherTab.bringToFront();
  await page.bringToFront();
  await page.evaluate(() => {
    // Headless Chromium does not reliably restore visibilityState after bringToFront.
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' });
    window.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => refreshes).toBeGreaterThan(0);
  await expect(table).toBeVisible();
  release();
  await expect(page.getByRole('table').first()).toBeVisible();
});
