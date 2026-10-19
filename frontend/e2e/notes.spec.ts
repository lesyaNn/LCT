import { expect, test } from '@playwright/test';
test('personal notes: editing, references, search, offline drafts, conflicts and deletion', async ({ page, context, request }, testInfo) => {
  test.skip(process.env.E2E_NOTES_ISOLATED !== '1', 'Requires a disposable notes stand (E2E_NOTES_ISOLATED=1).');
  const username = process.env.E2E_ADMIN_USERNAME;
  const password = process.env.E2E_ADMIN_PASSWORD;
  expect(username && password, 'Set E2E_ADMIN_USERNAME and E2E_ADMIN_PASSWORD').toBeTruthy();
  const base = process.env.E2E_BASE_URL || 'http://localhost:3000';
  const api = process.env.E2E_API_URL || 'http://localhost:8000';
  // Local QA can proxy one browser's requests to a temporary frontend while
  // retaining the existing Keycloak redirect origin. No shared server changes.
  const proxy = process.env.E2E_NOTES_FRONTEND_PROXY;
  let callbackUrl = '';
  if (proxy) await context.grantPermissions(['local-network-access']);
  if (proxy) await context.route(`${base}/**`, async (route) => {
    const target = new URL(route.request().url()).pathname.startsWith('/api/v1/') ? api : proxy;
    const response = await route.fetch({ url: route.request().url().replace(base, target) });
    await route.fulfill({ response });
  });
  if (proxy) await context.route('**/login-actions/authenticate*', async (route) => {
    // Redirect chains bypass the URL-specific frontend route above. Start the
    // callback as a fresh navigation so it reaches this build as well.
    const response = await route.fetch({ maxRedirects: 0 });
    callbackUrl = response.headers().location || '';
    if (callbackUrl) await route.fulfill({ status: 200, contentType: 'text/html', body: 'Returning to CRM…' });
    else await route.fulfill({ response });
  });
  let authorization = '';
  page.on('request', (req) => { if (req.url().includes('/api/v1/auth/me')) authorization = req.headers().authorization || authorization; });
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/notes');
  await page.getByRole('button', { name: /Войти через/ }).click({ timeout: 30_000 });
  await page.locator('input[name="username"]').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.locator('#kc-login').click();
  if (proxy) { await expect.poll(() => callbackUrl).not.toBe(''); await page.goto(callbackUrl); }
  await expect(page.getByRole('heading', { name: 'Заметки', exact: true })).toBeVisible();
  await expect.poll(() => authorization).toMatch(/^Bearer /);
  const headers = { authorization };
  const me = await (await request.get(`${api}/api/v1/auth/me`, { headers })).json();
  const userLookup = await request.get(`${api}/api/v1/notes/mentions?kind=user&q=${encodeURIComponent(username!)}`, { headers });
  expect(userLookup.status()).toBe(200);
  expect((await userLookup.json()).some((user: { id: string }) => user.id === me.id)).toBe(true);
  const title = `Notes E2E ${crypto.randomUUID()}`;
  const noteIds: string[] = [];
  let universityId = '';
  const rememberId = async () => {
    await expect(page).toHaveURL(/note=/);
    const id = new URL(page.url()).searchParams.get('note')!;
    if (!noteIds.includes(id)) noteIds.push(id);
    return id;
  };
  const saved = () => expect(page.getByRole('status').filter({ hasText: /^Сохранено$/ })).toBeVisible();
  const getNote = async (id: string) => {
    const response = await request.get(`${api}/api/v1/notes/${id}`, { headers });
    expect(response.status()).toBe(200);
    return response.json();
  };
  try {
    const university = await request.post(`${api}/api/v1/universities`, { headers, data: { name: `Notes test university ${crypto.randomUUID()}`, city: 'Москва' } });
    expect(university.status()).toBe(201);
    const universityData = await university.json(); universityId = universityData.id;
    const entities = await request.get(`${api}/api/v1/notes/mentions?kind=entity&q=${encodeURIComponent(universityData.name)}`, { headers });
    expect(entities.status()).toBe(200);
    expect((await entities.json()).some((entity: { id: string }) => entity.id === universityId)).toBe(true);
    await page.getByRole('button', { name: '+ Новая заметка' }).click();
    const id = await rememberId();
    await page.getByRole('textbox', { name: 'Заголовок заметки' }).fill(title);
    const text = page.getByRole('textbox', { name: 'Текст заметки' });
    await expect(page.getByRole('button', { name: 'Просмотр', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Редактирование', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: '+ Добавить блок' })).toHaveCount(0);
    await saved();
    const initial = await getNote(id);
    const markdown = '## Уже готовый заголовок\n\n**Сохранённый текст** и *курсив* и ~~зачеркнутый~~.\n\n- [ ] Проверить документы\n\n```\n- [ ] Это код\n```\n\n| Поле | Значение |\n| --- | --- |\n| Курс | CRM |';
    expect((await request.patch(`${api}/api/v1/notes/${id}`, { headers, data: { title, content: markdown, revision: initial.revision } })).status()).toBe(200);
    await page.reload();
    await expect(text.getByRole('heading', { name: 'Уже готовый заголовок' })).toBeVisible();
    await expect(text.locator('strong')).toHaveText('Сохранённый текст');
    await expect(text.getByRole('table')).toBeVisible();
    expect((await getNote(id)).content).toBe(markdown);
    await text.getByRole('checkbox').check();
    await saved();
    const withTask = await getNote(id);
    expect(withTask.content).toContain('[x] Проверить документы');
    expect(withTask.content).toContain('- [ ] Это код');
    await text.click();
    await text.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
    await text.press('Backspace');
    await text.pressSequentially('/');
    const menuScroll = await page.locator('main').evaluate((element) => element.scrollTop);
    await text.press('ArrowUp');
    const lastCommand = page.getByRole('option', { name: '/responsible Ответственные' });
    await expect(lastCommand).toHaveAttribute('aria-selected', 'true');
    await expect(lastCommand).toBeInViewport();
    expect(await page.locator('main').evaluate((element) => element.scrollTop)).toBe(menuScroll);
    await text.press('Escape'); await text.press('Backspace');
    await text.pressSequentially('/h2'); await text.press('Enter');
    await text.pressSequentially('План встречи');
    await expect(text.getByRole('heading', { level: 2, name: 'План встречи' })).toBeVisible();
    await text.press('Enter');
    await text.pressSequentially('**Обсудить программу**');
    await expect(text.locator('strong')).toHaveText('Обсудить программу');
    await text.press(process.platform === 'darwin' ? 'Meta+k' : 'Control+k');
    await expect(page.getByRole('textbox', { name: 'Адрес ссылки' })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Поиск по системе' })).toHaveAttribute('aria-expanded', 'false');
    await page.getByRole('textbox', { name: 'Адрес ссылки' }).press('Escape');
    await text.press('Enter');
    await text.pressSequentially('/university');
    const scrollBefore = await page.locator('main').evaluate((element) => element.scrollTop);
    const commandBounds = await page.getByRole('listbox', { name: 'Команды редактора' }).boundingBox();
    await text.press('Enter');
    await expect(page.getByRole('combobox', { name: 'Поиск сущности' })).toBeFocused();
    expect(Math.abs(await page.locator('main').evaluate((element) => element.scrollTop) - scrollBefore)).toBeLessThanOrEqual(1);
    const pickerBounds = await page.getByRole('combobox', { name: 'Поиск сущности' }).boundingBox();
    expect(pickerBounds!.y).toBeLessThan(commandBounds!.y + 130);
    await page.screenshot({ path: testInfo.outputPath('notes-picker.png'), fullPage: true });
    await page.getByRole('combobox', { name: 'Поиск сущности' }).fill(universityData.name);
    await expect(page.getByRole('option').filter({ hasText: universityData.name })).toBeVisible();
    await page.getByRole('combobox', { name: 'Поиск сущности' }).press('Enter');
    await expect(page.getByRole('link', { name: `@${universityData.name}`, exact: true })).toBeVisible();
    await saved();
    const stored = await getNote(id);
    expect(stored.content).toContain(`target_id=${universityId}`);
    expect(stored.content).toContain('**Обсудить программу**');
    await page.screenshot({ path: testInfo.outputPath('notes-desktop.png'), fullPage: true });

    // The real entity route opens from a resolved, permission-checked reference.
    await page.getByRole('link', { name: `@${universityData.name}`, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/universities/${universityId}`));
    await page.getByRole('link', { name: 'Заметки', exact: true }).click();
    await expect(page.getByRole('article', { name: 'Редактор заметки' })).toHaveCount(0);
    await page.getByRole('button').filter({ has: page.locator('strong', { hasText: title }) }).click();
    await expect(page.getByRole('textbox', { name: 'Заголовок заметки' })).toHaveValue(title);

    // A second note and list search must not destroy the first selection/text.
    await page.getByRole('button', { name: '+ Новая заметка' }).click();
    await expect(page).not.toHaveURL(new RegExp(id));
    await rememberId();
    await page.getByRole('textbox', { name: 'Заголовок заметки' }).fill(`${title} второй`);
    await page.getByRole('textbox', { name: 'Текст заметки' }).pressSequentially('Уникальный текст поиска');
    await saved();
    await page.getByRole('button', { name: '← Все заметки' }).click();
    await expect(page.getByRole('article', { name: 'Редактор заметки' })).toHaveCount(0);
    await page.screenshot({ path: testInfo.outputPath('notes-grid.png'), fullPage: true });
    await page.getByRole('searchbox', { name: 'Поиск заметок' }).fill('Уникальный текст поиска');
    await expect(page.getByRole('button').filter({ hasText: `${title} второй` })).toHaveCount(1);
    await page.getByRole('searchbox', { name: 'Поиск заметок' }).fill('');
    await page.getByRole('button').filter({ has: page.locator('strong', { hasText: title }) }).filter({ hasNotText: 'второй' }).click();
    await expect(page.getByRole('textbox', { name: 'Заголовок заметки' })).toHaveValue(title);
    await expect(page).toHaveURL(new RegExp(id));
    await page.goBack();
    await expect(page.getByRole('article', { name: 'Редактор заметки' })).toHaveCount(0);
    await page.goForward();
    await expect(page.getByRole('textbox', { name: 'Текст заметки' }).getByRole('heading', { name: 'План встречи' })).toBeVisible();
    await page.getByRole('combobox', { name: 'Поиск по системе' }).fill(title);
    await expect(page.getByRole('listbox', { name: 'Результаты поиска' }).getByText('Заметки', { exact: true })).toBeVisible();
    await page.getByRole('combobox', { name: 'Поиск по системе' }).press('Escape');

    // Keep unsaved text through a failed PATCH and a full page reload.
    let failSaves = true;
    await page.route('**/api/v1/notes/*', async (route) => {
      if (failSaves && route.request().method() === 'PATCH') await route.abort('failed');
      else await route.fallback();
    });
    await page.getByRole('textbox', { name: 'Заголовок заметки' }).fill(`${title} offline`);
    await expect(page.getByRole('alert').filter({ hasText: 'Текст остаётся в черновике' })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('textbox', { name: 'Заголовок заметки' })).toHaveValue(`${title} offline`);
    await expect(page.getByRole('alert').filter({ hasText: 'Текст остаётся в черновике' })).toBeVisible();
    failSaves = false;
    await page.getByRole('button', { name: 'Повторить сохранение' }).click(); await saved();
    expect((await getNote(id)).title).toBe(`${title} offline`);

    // A concurrent server change is never overwritten automatically.
    const before = await getNote(id);
    expect((await request.patch(`${api}/api/v1/notes/${id}`, { headers, data: { title: `${title} remote`, content: before.content, revision: before.revision } })).status()).toBe(200);
    await page.getByRole('textbox', { name: 'Заголовок заметки' }).fill(`${title} local`);
    await expect(page.getByRole('button', { name: 'Сохранить копию моего текста' })).toBeVisible();
    expect((await getNote(id)).title).toBe(`${title} remote`);
    await page.getByRole('button', { name: 'Сохранить копию моего текста' }).click();
    await expect(page).not.toHaveURL(new RegExp(id));
    const copyId = await rememberId(); expect(copyId).not.toBe(id); await saved();
    expect((await getNote(copyId)).title).toContain('local');

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByRole('button', { name: '← Все заметки' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('notes-mobile.png'), fullPage: true });
    expect((await request.delete(`${api}/api/v1/universities/${universityId}`, { headers })).status()).toBe(204);
    await page.getByRole('link', { name: `@${universityData.name}`, exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Объект удалён или недоступен' })).toBeVisible();
    await page.getByRole('button', { name: 'Удалить', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Отмена' }).click();
    expect((await getNote(copyId)).id).toBe(copyId);
    await page.getByRole('button', { name: 'Удалить', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
    await expect.poll(async () => (await request.get(`${api}/api/v1/notes/${copyId}`, { headers })).status()).toBe(404);
    await expect(page.getByRole('article', { name: 'Редактор заметки' })).toHaveCount(0);
    expect(errors).toEqual([]);
  } finally {
    for (const id of noteIds) {
      const response = await request.get(`${api}/api/v1/notes/${id}`, { headers });
      if (response.ok()) { const note = await response.json(); await request.delete(`${api}/api/v1/notes/${id}?revision=${note.revision}`, { headers }); }
    }
    if (universityId) await request.delete(`${api}/api/v1/universities/${universityId}`, { headers });
  }
});
