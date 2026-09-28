import { expect, test, type Page } from '@playwright/test';

async function login(page: Page, username = process.env.E2E_ADMIN_USERNAME ?? '', password = process.env.E2E_ADMIN_PASSWORD ?? '') {
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
}

test('full Workflow history, comment edit with file, and shared modals', async ({ page, browser }) => {
  const instanceId = process.env.E2E_WORKFLOW_INSTANCE_ID;
  test.skip(!instanceId || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD);
  await login(page);
  await page.goto(`/workflows/${instanceId}`);
  const history = page.locator('section[aria-labelledby$="-transition-title"]');
  await expect(history.getByRole('heading', { name: 'История Workflow' })).toBeVisible();
  const events = history.locator('ol > li');
  await expect(events.first()).toBeVisible();
  const before = await events.count();
  expect(before).toBeGreaterThanOrEqual(3);
  await expect(history.getByText('Этап изменён').first()).toBeVisible();
  const stageButtons = page.locator('section[aria-labelledby$="-stages-title"] button');
  await stageButtons.first().click();
  await expect(events).toHaveCount(before);
  await stageButtons.last().click();
  await expect(events).toHaveCount(before);
  await page.getByTestId('workflow-current-stage').click();

  const comments = page.locator('section[aria-labelledby$="-comments-title"]');
  const marker = `history-${Date.now()}`;
  await comments.getByRole('textbox', { name: 'Добавить комментарий' }).fill(marker);
  await comments.locator('input[type="file"]').setInputFiles({ name: `${marker}.pdf`, mimeType: 'application/pdf', buffer: Buffer.from('history file') });
  await comments.getByRole('button', { name: 'Отправить' }).click();
  await expect(comments.getByText(marker, { exact: true })).toBeVisible();
  await expect(history.getByText(marker, { exact: true })).toBeVisible();
  await expect(history.getByRole('button', { name: `Скачать ${marker}.pdf` })).toBeVisible();

  await comments.getByRole('button', { name: /Редактировать комментарий/ }).first().click();
  await comments.getByRole('textbox', { name: 'Редактировать комментарий' }).fill(`${marker}-edited`);
  await comments.getByRole('button', { name: 'Сохранить' }).click();
  await expect(history.getByText(`${marker}-edited`, { exact: true })).toBeVisible();
  await page.reload();
  await expect(history.getByText(`${marker}-edited`, { exact: true })).toBeVisible();
  await expect(history.getByRole('button', { name: `Скачать ${marker}.pdf` })).toBeVisible();
  const download = page.waitForEvent('download');
  await history.getByRole('button', { name: `Скачать ${marker}.pdf` }).click();
  expect((await download).suggestedFilename()).toBe(`${marker}.pdf`);
  await expect(events).toHaveCount(before + 1);

  if (process.env.E2E_MANAGER_USERNAME && process.env.E2E_MANAGER_PASSWORD) {
    const otherContext = await browser.newContext();
    const other = await otherContext.newPage();
    await login(other, process.env.E2E_MANAGER_USERNAME, process.env.E2E_MANAGER_PASSWORD);
    await other.goto(`/workflows/${instanceId}`);
    await expect(other.locator('main')).toContainText(/Не удалось загрузить данные|История Workflow/);
    if (await other.getByRole('heading', { name: 'Не удалось загрузить данные' }).isVisible().catch(() => false)) {
      await expect(other.getByRole('heading', { name: 'Не удалось загрузить данные' })).toBeVisible();
    } else {
      const otherComments = other.locator('section[aria-labelledby$="-comments-title"]');
      const ownRecord = otherComments.locator('ul > li').filter({ hasText: `${marker}-edited` }).first();
      await expect(ownRecord).toBeVisible();
      await expect(ownRecord.getByRole('button', { name: /Редактировать комментарий/ })).toHaveCount(0);
    }
    await otherContext.close();
  }

  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const info = page.locator('section[aria-labelledby$="-overview-title"]');
    for (const [field, title] of [['Дедлайн', 'Дедлайн этапа'], ['Ответственный Workflow', 'Ответственный Workflow']] as const) {
      const row = info.locator('div').filter({ has: page.getByText(field, { exact: true }) }).last();
      await row.getByRole('button', { name: /Установить|Изменить|Назначить/ }).click();
      const dialog = page.getByRole('dialog', { name: title });
      const heading = await dialog.getByRole('heading', { name: title }).boundingBox();
      const close = await dialog.getByRole('button', { name: 'Закрыть' }).boundingBox();
      const box = await dialog.boundingBox();
      expect(heading && close && box).toBeTruthy();
      expect(close!.x).toBeGreaterThan(heading!.x + heading!.width);
      expect(close!.x + close!.width).toBeLessThanOrEqual(box!.x + box!.width);
      await dialog.getByRole('button', { name: 'Закрыть' }).click();
    }
  }
});

test('contract and license filters use backend status and university params', async ({ page }) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD);
  await login(page);
  await page.goto('/admin/catalogs');
  await page.locator('#catalog-tab-agreements').click();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByTestId('catalog-agreements-contracts').click();
    if (width === 1440 && await page.getByRole('button', { name: 'Вперёд' }).isEnabled().catch(() => false)) {
      await page.getByRole('button', { name: 'Вперёд' }).click();
      await expect(page.getByText(/Страница 2 из/)).toBeVisible();
    }
    const drawer = width === 390 ? page.getByRole('button', { name: 'Фильтры' }) : null;
    if (drawer) await drawer.click();
    const scope = drawer ? page.getByRole('dialog', { name: 'Фильтры' }) : page;
    const university = scope.getByRole('combobox', { name: 'ВУЗ' });
    await expect(university.locator('option')).not.toHaveCount(1);
    const universityId = await university.locator('option').nth(1).getAttribute('value');
    await university.selectOption(universityId!);
    await expect(page.getByText(/Страница 1 из/)).toBeVisible();
    const status = scope.getByRole('combobox', { name: 'Состояние' });
    const request = width === 1440 ? page.waitForRequest((item) => item.url().includes('/api/v1/contracts?') && item.url().includes('status=active') && item.url().includes(`university_id=${universityId}`)) : null;
    await status.selectOption('active');
    if (request) await request;
    await scope.getByRole('button', { name: 'Сбросить', exact: true }).click();
    await expect(status).toHaveValue('');
    await expect(university).toHaveValue('');
    if (drawer) await scope.getByRole('button', { name: 'Показать результаты' }).click();
    await page.getByTestId('catalog-agreements-licenses').click();
    if (drawer) await drawer.click();
    const licenseScope = drawer ? page.getByRole('dialog', { name: 'Фильтры' }) : page;
    const licenseStatus = licenseScope.getByRole('combobox', { name: 'Состояние' });
    const licenseRequest = width === 1440 ? page.waitForRequest((item) => item.url().includes('/api/v1/licenses?') && item.url().includes('status=expires_soon')) : null;
    await licenseStatus.selectOption('expires_soon');
    if (licenseRequest) await licenseRequest;
    await licenseScope.getByRole('button', { name: 'Сбросить', exact: true }).click();
    if (drawer) await licenseScope.getByRole('button', { name: 'Показать результаты' }).click();
  }
});
