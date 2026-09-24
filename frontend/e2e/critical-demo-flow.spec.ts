import { stat } from 'node:fs/promises';
import { expect, test, type Page, type TestInfo } from '@playwright/test';

type SmokeConfig = {
  baseURL: URL;
  managerUsername: string;
  managerPassword: string;
  universityId: string;
  universityName: string;
  workflowInstanceId: string;
  expectedWorkflowStage: string;
  runId: string;
};

function requiredEnvironment(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(
      `E2E preflight failed: ${name} is required. Configure the dedicated Keycloak manager and resettable demo fixture in the environment.`,
    );
  }
  return value;
}

function smokeConfig(): SmokeConfig {
  const baseURL = new URL(process.env.E2E_BASE_URL?.trim() || 'http://localhost:3000');
  return {
    baseURL,
    managerUsername: requiredEnvironment('E2E_MANAGER_USERNAME'),
    managerPassword: requiredEnvironment('E2E_MANAGER_PASSWORD'),
    universityId: requiredEnvironment('E2E_UNIVERSITY_ID'),
    universityName: requiredEnvironment('E2E_UNIVERSITY_NAME'),
    workflowInstanceId: requiredEnvironment('E2E_WORKFLOW_INSTANCE_ID'),
    expectedWorkflowStage: requiredEnvironment('E2E_EXPECTED_WORKFLOW_STAGE'),
    runId: process.env.E2E_RUN_ID?.trim() || process.env.SOURCECRAFT_RUN_ID?.trim() || 'local',
  };
}

async function checkpoint(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path, fullPage: true });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

function jsonRecord(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('E2E contract mismatch: API response must be a JSON object.');
  }
  return value as Record<string, unknown>;
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`E2E contract mismatch: response field ${field} is missing.`);
  }
  return value;
}

test('manager completes the critical ten-step demo flow', async ({ page }, testInfo) => {
  const config = smokeConfig();
  const transitionComment = `E2E ${config.runId}: этап проверен и готов к переходу.`;
  const stageComment = `E2E ${config.runId}: подтверждение текущего этапа.`;
  let targetStageName = '';

  await test.step('1. Login через Keycloak как manager', async () => {
    await page.goto('/login');
    const loginButton = page.getByRole('button', { name: 'Войти через Keycloak' });
    await expect(loginButton).toBeVisible();
    await loginButton.click();

    await expect(page.locator('input[name="username"]')).toBeVisible();
    await page.locator('input[name="username"]').fill(config.managerUsername);
    await page.locator('input[name="password"]').fill(config.managerPassword);
    await page.getByRole('button', { name: /Войти|Sign in|Log in/i }).click();

    await page.waitForURL((url) => url.origin === config.baseURL.origin && url.pathname === '/dashboard');
    await expect(page.getByRole('button', { name: /Менеджер/ })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Отчёты' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Аудит' })).toBeVisible();
  });

  await test.step('2. Dashboard: KPI и основные графики загрузились', async () => {
    await expect(page.getByRole('heading', { name: 'Обзор', level: 1 })).toBeVisible();
    await expect(page.getByTestId('dashboard-kpi')).toBeVisible();
    await expect(page.getByRole('img', { name: 'Распределение вузов по диапазонам Health Score' })).toBeVisible();
    await expect(page.getByRole('img', { name: 'Распределение программ по статусам' })).toBeVisible();
    await expect(page.getByRole('img', { name: 'Динамика фактических и планируемых запусков программ за 12 месяцев' })).toBeVisible();
    await expect(page.getByTestId('chart-export-health-distribution')).toBeVisible();
    await expect(page.getByTestId('chart-export-programs')).toBeVisible();
    await expect(page.getByTestId('chart-export-dynamics')).toBeVisible();
    await expect(page.getByTestId('chart-export-attention')).toBeVisible();
    await checkpoint(page, testInfo, '01-dashboard');
  });

  await test.step('3. Universities: открыть стабильный ВУЗ', async () => {
    await page.getByRole('link', { name: 'ВУЗы' }).click();
    await page.waitForURL((url) => url.origin === config.baseURL.origin && url.pathname === '/universities');
    const universityRow = page.getByTestId(`university-row-${config.universityId}`);
    await expect(universityRow).toBeVisible();
    await universityRow.getByRole('link', { name: config.universityName, exact: true }).click();
    await page.waitForURL((url) => url.pathname === `/universities/${config.universityId}`);
    await expect(page.getByRole('heading', { name: config.universityName, level: 1 })).toBeVisible();
  });

  await test.step('4. Passport → Health Score: score, breakdown и reasons видны', async () => {
    await page.getByRole('tab', { name: 'Health Score' }).click();
    await expect(page).toHaveURL(new RegExp(`/universities/${config.universityId}\\?tab=health-score`));
    await expect(page.getByRole('img', { name: /Health Score \d+ из 100/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Состав оценки', level: 2 })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Причины', level: 2 })).toBeVisible();
    await expect(page.getByTestId('chart-export-health-score-dynamics')).toBeVisible();
    await checkpoint(page, testInfo, '02-health-score');
  });

  await test.step('5. Passport → Workflow: текущий этап виден', async () => {
    await page.getByRole('tab', { name: 'Workflow' }).click();
    await expect(page).toHaveURL(new RegExp(`/universities/${config.universityId}\\?tab=workflow`));
    await expect(page.getByTestId('workflow-current-stage')).toBeVisible();

    // Passport fixtures and the write-capable Workflow API currently use
    // different identifiers. The dedicated API instance is supplied by the
    // test stand and remains part of the same user-visible Workflow journey.
    const workflowResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'GET'
      && response.url().includes(`/api/v1/workflow/instances/${config.workflowInstanceId}`)
    ));
    await page.goto(`/workflows/${config.workflowInstanceId}`);
    const workflowResponse = await workflowResponsePromise;
    expect(workflowResponse.ok(), `Workflow fixture lookup returned ${workflowResponse.status()}`).toBeTruthy();
    await expect(page.getByRole('heading', { name: 'Взаимодействие с вузом', level: 1 })).toBeVisible();
    await expect(page.getByTestId('workflow-current-stage')).toContainText(config.expectedWorkflowStage);
  });

  await test.step('6. Перевести Workflow на следующий этап', async () => {
    await page.getByRole('button', { name: 'Перевести на следующий этап' }).click();
    const dialog = page.getByRole('dialog', { name: 'Перевести на следующий этап' });
    await expect(dialog).toBeVisible();
    const nextStageText = await dialog.getByText(/^Следующий:/).textContent();
    targetStageName = nextStageText?.replace(/^Следующий:\s*\d+\.\s*/, '').trim() || '';
    expect(targetStageName, 'Transition modal must expose the target stage name').not.toBe('');
    await dialog.getByLabel('Комментарий').fill(transitionComment);

    const transitionResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && response.url().includes(`/api/v1/workflow/instances/${config.workflowInstanceId}/transition`)
    ));
    await dialog.getByRole('button', { name: 'Перевести', exact: true }).click();
    const transitionResponse = await transitionResponsePromise;
    expect(transitionResponse.ok(), `Workflow transition returned ${transitionResponse.status()}`).toBeTruthy();
    const transitionPayload = jsonRecord(await transitionResponse.json());
    requiredString(transitionPayload.current_instance_stage_id, 'current_instance_stage_id');

    await expect(page.getByRole('status').filter({ hasText: 'Этап успешно переведён' })).toBeVisible();
    await expect(page.getByTestId('workflow-current-stage')).toContainText(targetStageName);
    await checkpoint(page, testInfo, '03-workflow-after-transition');
  });

  await test.step('7. Добавить комментарий в текущий этап', async () => {
    const editor = page.getByLabel('Добавить комментарий');
    await expect(editor).toBeEnabled();
    await editor.fill(stageComment);
    const commentResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && response.url().includes(`/api/v1/workflow/instances/${config.workflowInstanceId}/comments`)
    ));
    await page.getByRole('button', { name: 'Отправить', exact: true }).click();
    const commentResponse = await commentResponsePromise;
    expect(commentResponse.ok(), `Workflow comment returned ${commentResponse.status()}`).toBeTruthy();
    await expect(page.getByText(stageComment, { exact: true })).toBeVisible();
  });

  await test.step('8. Reports: выбрать параметры и XLSX', async () => {
    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Отчёты', level: 1 })).toBeVisible();
    await page.getByRole('checkbox', { name: 'Health Score' }).check();
    const xlsx = page.getByRole('radio', { name: /^XLSX/ });
    await xlsx.check();
    await expect(xlsx).toBeChecked();
  });

  await test.step('9. Сформировать, дождаться ready и скачать непустой XLSX', async () => {
    const createResponsePromise = page.waitForResponse((response) => (
      response.request().method() === 'POST'
      && response.url().includes('/api/v1/reports/export')
    ));
    await page.getByRole('button', { name: 'Сформировать отчёт' }).click();
    const createResponse = await createResponsePromise;
    expect(createResponse.ok(), `Report create returned ${createResponse.status()}`).toBeTruthy();
    const createPayload = jsonRecord(await createResponse.json());
    const reportJobId = requiredString(createPayload.job_id ?? createPayload.id, 'job_id');
    const reportJob = page.getByTestId(`report-job-${reportJobId}`);
    await expect(reportJob).toContainText('Готов', { timeout: 75_000 });
    await checkpoint(page, testInfo, '04-report-ready');

    const downloadPromise = page.waitForEvent('download');
    await reportJob.getByRole('link', { name: /Скачать/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename().toLocaleLowerCase()).toMatch(/\.xlsx$/);
    const downloadPath = await download.path();
    expect(downloadPath, 'Downloaded XLSX must have a local path').not.toBeNull();
    const downloadedFile = await stat(downloadPath as string);
    expect(downloadedFile.size, 'Downloaded XLSX must not be empty').toBeGreaterThan(0);
  });

  await test.step('10. Audit: найти именно выполненный transition', async () => {
    await page.goto('/audit');
    await expect(page.getByRole('heading', { name: 'Аудит действий', level: 1 })).toBeVisible();
    const matchingEvents = page.getByTestId('audit-event')
      .filter({ hasText: 'Переход Workflow' })
      .filter({ hasText: config.workflowInstanceId })
      .filter({ hasText: targetStageName });
    await expect(matchingEvents).toHaveCount(1);
    await expect(matchingEvents).toBeVisible();
    await checkpoint(page, testInfo, '05-audit-transition');
  });
});
