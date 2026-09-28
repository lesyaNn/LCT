import { expect, test } from '@playwright/test';
import { createIsolatedWorkflow, loginForWorkflowE2E, validTestPdf } from './workflow-isolated-fixture';

test('comment and Workflow attachments upload, persist after reload and download', async ({ page, request }) => {
  test.skip(process.env.E2E_DISPOSABLE_DB !== '1' || !process.env.E2E_WORKFLOW_UNIVERSITY_ID || !process.env.E2E_ADMIN_USERNAME || !process.env.E2E_ADMIN_PASSWORD,
    'Requires a disposable real DB, university, and E2E_ADMIN credentials.');
  const authorization = await loginForWorkflowE2E(page);
  const instanceId = await createIsolatedWorkflow(request, authorization);
  await page.goto(`/workflows/${instanceId}`);

  if (process.env.E2E_COMPLETED_WORKFLOW_STAGE && process.env.E2E_CURRENT_WORKFLOW_STAGE) {
    await page.getByRole('button', { name: new RegExp(process.env.E2E_COMPLETED_WORKFLOW_STAGE) }).first().click();
    await expect(page.locator('section[aria-labelledby$="-comments-title"] input[type="file"]')).toHaveCount(0);
    await page.getByRole('button', { name: new RegExp(process.env.E2E_CURRENT_WORKFLOW_STAGE) }).first().click();
  }

  const comments = page.locator('section[aria-labelledby$="-comments-title"]').first();
  const picker = comments.locator('input[type="file"]');
  await expect(picker).toBeAttached();
  await expect(page.locator('section[aria-labelledby$="-attachments-title"] input[type="file"]')).toHaveCount(0);
  const marker = `comment-file-${Date.now()}`;
  await comments.getByRole('textbox', { name: 'Добавить комментарий' }).fill(marker);
  await picker.setInputFiles({ name: 'invalid.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('bad') });
  await expect(comments.getByRole('alert')).toContainText('Тип файла');
  await expect(comments.getByRole('textbox', { name: 'Добавить комментарий' })).toHaveValue(marker);
  await picker.setInputFiles([
    { name: `${marker}-1.pdf`, mimeType: 'application/pdf', buffer: validTestPdf('first') },
    { name: `${marker}-2.pdf`, mimeType: 'application/pdf', buffer: validTestPdf('second') },
  ]);
  await expect(comments.getByText(`${marker}-1.pdf`)).toBeVisible();
  await expect(comments.getByText('Загрузил:')).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Общие материалы Workflow' }).getByText(`${marker}-1.pdf`)).toHaveCount(0);
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
  const currentStage = page.getByTestId('workflow-current-stage');
  await expect(currentStage).toContainText('Комментарии 1');
  await expect(currentStage).toContainText('Вложения 2');
  const orange = await currentStage.evaluate((button) => {
    const marker = button.querySelector('[aria-hidden="true"]');
    const badge = button.querySelector('span[class*="status-badge-module"]');
    return {
      left: getComputedStyle(button).borderLeftColor,
      markerBorder: marker ? getComputedStyle(marker).borderColor : '',
      markerColor: marker ? getComputedStyle(marker).color : '',
      badgeColor: badge ? getComputedStyle(badge).color : '',
    };
  });
  expect(orange.left).toBe(orange.markerBorder);
  expect(orange.badgeColor).toBe(orange.markerColor);
  const download = page.waitForEvent('download');
  const downloadRequest = page.waitForEvent('request', (request) => request.url().includes('/attachments/') && request.url().endsWith('/download'));
  await comments.getByRole('button', { name: `Скачать ${marker}-1.pdf` }).click();
  const downloaded = await download;
  expect(downloaded.suggestedFilename()).toBe(`${marker}-1.pdf`);
  const bytes: Buffer[] = [];
  for await (const chunk of (await downloaded.createReadStream())!) bytes.push(Buffer.from(chunk));
  expect(Buffer.concat(bytes)).toEqual(validTestPdf('first'));
  expect((await downloadRequest).headers().authorization).toMatch(/^Bearer /);

  const taskTitle = `Task ${Date.now()}`;
  await page.getByRole('button', { name: '+ Добавить задачу' }).click();
  await page.getByRole('textbox', { name: 'Новая задача' }).fill(taskTitle);
  await page.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText(taskTitle, { exact: true })).toBeVisible();
  await expect(currentStage).toContainText('Задачи 1');

  const generalName = `general-${Date.now()}.pdf`;
  const generalResponse = await request.post(`${process.env.E2E_API_URL ?? 'http://localhost:8000'}/api/v1/workflow/instances/${instanceId}/attachments`, {
    headers: { authorization },
    multipart: { file: { name: generalName, mimeType: 'application/pdf', buffer: validTestPdf('general') } },
  });
  expect(generalResponse.status(), await generalResponse.text()).toBe(201);
  await page.reload();
  const general = page.getByRole('region', { name: 'Общие материалы Workflow' });
  await expect(general).toBeVisible();
  await expect(general.locator('details')).not.toHaveAttribute('open');
  await expect(general.getByText(generalName)).not.toBeVisible();
  await general.locator('summary').click();
  await expect(general.getByText(generalName)).toBeVisible();
  await expect(comments.getByText(generalName)).toHaveCount(0);
  const generalDownload = page.waitForEvent('download');
  await general.getByRole('button', { name: `Скачать ${generalName}` }).first().click();
  const generalBytes: Buffer[] = [];
  for await (const chunk of (await (await generalDownload).createReadStream())!) generalBytes.push(Buffer.from(chunk));
  expect(Buffer.concat(generalBytes)).toEqual(validTestPdf('general'));

  const history = page.locator('section[aria-labelledby$="-transition-title"]');
  await history.locator('details').first().locator('summary').first().click();
  await history.locator('details details').filter({ hasText: marker }).first().locator('summary').click();
  await expect(history.getByText(marker, { exact: true })).toBeVisible();
  await expect(history.getByText(/Комментарий · Demo Admin/).first()).toBeVisible();
  await expect(history.getByRole('button', { name: `Скачать ${marker}-1.pdf` })).toBeVisible();
  for (const width of [1440, 768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(currentStage).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  const otherStage = page.locator('section[aria-labelledby$="-stages-title"] ol > li > button').nth(1);
  await otherStage.click();
  await expect(currentStage).toHaveAttribute('aria-current', 'step');
  const accents = await otherStage.evaluate((button) => ({
    selected: getComputedStyle(button).borderLeftColor,
    current: getComputedStyle(document.querySelector('[data-testid="workflow-current-stage"]')!).borderLeftColor,
  }));
  expect(accents.selected).not.toBe(accents.current);
  await currentStage.click();

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
