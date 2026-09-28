import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';

async function createJob(page: Page, expectedFormat: string) {
  const responsePromise = page.waitForResponse((response) => response.request().method() === 'POST' && response.url().endsWith('/api/v1/reports'));
  await page.getByRole('button', { name: 'Сформировать отчёт' }).click();
  const response = await responsePromise;
  expect(response.status()).toBe(202);
  const payload = response.request().postDataJSON();
  expect(payload.format).toBe(expectedFormat);
  const { job_id: id, status } = await response.json();
  expect(status).toBe('queued');
  expect(id).toMatch(/^[0-9a-f-]{36}$/);
  const row = page.getByTestId(`report-job-${id}`);
  await expect(row).toContainText('Готов', { timeout: 60_000 });
  return { id: id as string, payload };
}

test('real report, download, template and responsive queue', async ({ page }, testInfo) => {
  test.skip(!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD, 'Requires local admin credentials.');
  await page.goto('/login');
  const keycloak = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloak.isVisible().catch(() => false)) await keycloak.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await page.goto('/reports');

  const parameters = page.getByRole('heading', { name: 'Параметры отчёта' }).locator('../..');
  const queue = page.locator('section[aria-labelledby="report-jobs-heading"]');
  await expect(parameters).toBeVisible();
  await expect(queue).toBeVisible();
  const left = await parameters.boundingBox();
  const right = await queue.boundingBox();
  expect(left && right && left.x + left.width <= right.x + 2).toBeTruthy();

  const simple = await createJob(page, 'xlsx');
  const card = queue.locator('article').first();
  await expect(card).toContainText('Готов');
  const responsePromise = page.waitForResponse((response) => response.url().includes(`/api/v1/reports/${simple.id}/download`));
  const downloadPromise = page.waitForEvent('download');
  await card.getByRole('button', { name: 'Скачать' }).click();
  const response = await responsePromise;
  const download = await downloadPromise;
  expect(response.status()).toBe(200);
  expect(response.headers()['content-type']).toContain('spreadsheetml.sheet');
  expect(response.headers()['content-disposition']).toContain(`report_${simple.id}.xlsx`);
  const savedPath = testInfo.outputPath(`report_${simple.id}.xlsx`);
  await download.saveAs(savedPath);
  expect(readFileSync(savedPath).subarray(0, 2).toString()).toBe('PK');

  await page.reload();
  await expect(page.getByTestId(`report-job-${simple.id}`)).toContainText('Готов');
  await page.getByLabel('От', { exact: true }).fill('2026-01-01');
  await page.getByLabel('До', { exact: true }).fill('2026-12-31');
  await page.getByRole('checkbox', { name: 'Город' }).check();
  await page.getByRole('radio', { name: /PDF/ }).check();

  const templateName = `QA отчёт ${Date.now()}`;
  await page.getByLabel('Название шаблона').fill(templateName);
  const templateResponse = page.waitForResponse((item) => item.request().method() === 'POST' && item.url().endsWith('/api/v1/reports/templates'));
  await page.getByRole('button', { name: 'Сохранить', exact: true }).click();
  expect((await templateResponse).status()).toBe(201);
  await expect(page.getByRole('button', { name: templateName, exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: templateName, exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'По ТЗ', exact: true }).click();
  await page.getByRole('button', { name: templateName, exact: true }).click();
  await expect(page.getByLabel('От', { exact: true })).toHaveValue('2026-01-01');
  await expect(page.getByRole('checkbox', { name: 'Город' })).toBeChecked();
  await expect(page.getByRole('radio', { name: /PDF/ })).toBeChecked();

  const filtered = await createJob(page, 'pdf');
  expect(filtered.payload.filters.date_from).toBe('2026-01-01');
  expect(filtered.payload.filters.date_to).toBe('2026-12-31');
  expect(filtered.payload.columns).toContain('city');
  const pdfCard = queue.locator('article').first();
  const pdfResponsePromise = page.waitForResponse((item) => item.url().includes(`/api/v1/reports/${filtered.id}/download`));
  const pdfDownloadPromise = page.waitForEvent('download');
  await pdfCard.getByRole('button', { name: 'Скачать' }).click();
  const pdfResponse = await pdfResponsePromise;
  const pdfDownload = await pdfDownloadPromise;
  expect(pdfResponse.status()).toBe(200);
  expect(pdfResponse.headers()['content-type']).toContain('application/pdf');
  expect(pdfResponse.headers()['content-disposition']).toContain(`report_${filtered.id}.pdf`);
  const pdfPath = testInfo.outputPath(`report_${filtered.id}.pdf`);
  await pdfDownload.saveAs(pdfPath);
  expect(readFileSync(pdfPath).subarray(0, 4).toString()).toBe('%PDF');

  await page.getByRole('radio', { name: /^XLS\s/ }).check();
  const legacy = await createJob(page, 'xls');
  const xlsResponsePromise = page.waitForResponse((item) => item.url().includes(`/api/v1/reports/${legacy.id}/download`));
  const xlsDownloadPromise = page.waitForEvent('download');
  await queue.locator('article').first().getByRole('button', { name: 'Скачать' }).click();
  const xlsResponse = await xlsResponsePromise;
  const xlsDownload = await xlsDownloadPromise;
  expect(xlsResponse.status()).toBe(200);
  expect(xlsResponse.headers()['content-type']).toContain('application/vnd.ms-excel');
  expect(xlsResponse.headers()['content-disposition']).toContain(`report_${legacy.id}.xls`);
  const xlsPath = testInfo.outputPath(`report_${legacy.id}.xls`);
  await xlsDownload.saveAs(xlsPath);
  expect(readFileSync(xlsPath).subarray(0, 8).toString('hex')).toBe('d0cf11e0a1b11ae1');

  const closeNotification = page.getByRole('button', { name: 'Закрыть уведомление' });
  while (await closeNotification.count()) await closeNotification.first().click();
  for (const width of [1440, 1024, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole('heading', { name: 'Параметры отчёта' }).scrollIntoViewIfNeeded();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width + 1);
    if (width === 1440 || width === 390) await page.screenshot({ path: testInfo.outputPath(`reports-${width}.png`) });
    const formBox = await parameters.boundingBox();
    const queueBox = await queue.boundingBox();
    if (width < 1180) expect(formBox && queueBox && formBox.y + formBox.height <= queueBox.y + 2).toBeTruthy();
  }
  await page.getByRole('button', { name: `Удалить шаблон ${templateName}` }).click();
});
