import { expect, test } from '@playwright/test';

test('comment attachments upload once, persist after reload and download', async ({ page }) => {
  const instanceId = process.env.E2E_WORKFLOW_INSTANCE_ID;
  const mockAuth = process.env.E2E_MOCK_AUTH === '1';
  test.skip(!instanceId || (!mockAuth && (!process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD)),
    'Requires a writable workflow fixture and E2E_ADMIN credentials or local mock auth.');

  if (!mockAuth) {
    await page.goto('/login');
    const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
    if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
    await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
    await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
    await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
    await page.waitForURL((url) => url.pathname === '/dashboard');
  }
  await page.goto(`/workflows/${instanceId}`);

  if (process.env.E2E_COMPLETED_WORKFLOW_STAGE && process.env.E2E_CURRENT_WORKFLOW_STAGE) {
    await page.getByRole('button', { name: new RegExp(process.env.E2E_COMPLETED_WORKFLOW_STAGE) }).first().click();
    await expect(page.locator('section[aria-labelledby$="-comments-title"] input[type="file"]')).toHaveCount(0);
    await page.getByRole('button', { name: new RegExp(process.env.E2E_CURRENT_WORKFLOW_STAGE) }).first().click();
  }

  const comments = page.locator('section[aria-labelledby$="-comments-title"]').first();
  const picker = comments.locator('input[type="file"]');
  await expect(picker).toBeAttached();
  const marker = `comment-file-${Date.now()}`;
  await comments.getByRole('textbox', { name: 'Добавить комментарий' }).fill(marker);
  await picker.setInputFiles({ name: 'invalid.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('bad') });
  await expect(comments.getByRole('alert')).toContainText('Тип файла');
  await expect(comments.getByRole('textbox', { name: 'Добавить комментарий' })).toHaveValue(marker);
  await picker.setInputFiles([
    { name: `${marker}-1.pdf`, mimeType: 'application/pdf', buffer: Buffer.from('first') },
    { name: `${marker}-2.pdf`, mimeType: 'application/pdf', buffer: Buffer.from('second') },
  ]);
  await expect(comments.getByText(`${marker}-1.pdf`)).toBeVisible();
  let uploads = 0;
  let uploadAuthorization = '';
  let uploadContentType = '';
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith(`/workflow/instances/${instanceId}/comments/with-attachments`)) {
      uploads += 1;
      uploadAuthorization = request.headers().authorization ?? '';
      uploadContentType = request.headers()['content-type'] ?? '';
    }
  });
  await comments.getByRole('button', { name: 'Отправить' }).click();
  await expect(comments.getByText(marker, { exact: true })).toBeVisible();
  expect(uploads).toBe(1);
  expect(uploadAuthorization).toMatch(/^Bearer /);
  expect(uploadContentType).toMatch(/^multipart\/form-data; boundary=/);
  await page.reload();
  await expect(comments.getByText(marker, { exact: true })).toBeVisible();
  await expect(comments.getByText(`${marker}-1.pdf`)).toBeVisible();
  const download = page.waitForEvent('download');
  const downloadRequest = page.waitForEvent('request', (request) => request.url().includes('/attachments/') && request.url().endsWith('/download'));
  await comments.getByRole('button', { name: `Скачать ${marker}-1.pdf` }).click();
  expect((await download).suggestedFilename()).toBe(`${marker}-1.pdf`);
  expect((await downloadRequest).headers().authorization).toMatch(/^Bearer /);

  const plain = `${marker}-plain`;
  await comments.getByRole('textbox', { name: 'Добавить комментарий' }).fill(plain);
  await comments.getByRole('button', { name: 'Отправить' }).click();
  await expect(comments.getByText(plain, { exact: true })).toBeVisible();

  const failed = `${marker}-failed`;
  await page.route(`**/workflow/instances/${instanceId}/comments/with-attachments`, (route) => route.abort('failed'));
  await comments.getByRole('textbox', { name: 'Добавить комментарий' }).fill(failed);
  await picker.setInputFiles({ name: 'retry.pdf', mimeType: 'application/pdf', buffer: Buffer.from('retry') });
  await comments.getByRole('button', { name: 'Отправить' }).click();
  await expect(comments.getByRole('textbox', { name: 'Добавить комментарий' })).toHaveValue(failed);
  await expect(comments.getByText('retry.pdf', { exact: false })).toBeVisible();
});
