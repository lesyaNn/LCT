import { resolve } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

test.skip(process.env.E2E_MOCK_MODE !== '1', 'Run against a dev server with mock auth and data.');

async function expectImportScrollEndsAtContent(page: Page) {
  const metrics = await page.evaluate(() => {
    const main = document.querySelector('main');
    const journal = document.querySelector('section[aria-labelledby="import-jobs-heading"]');
    const sidebar = document.querySelector('aside');
    if (!main || !journal) throw new Error('Import layout is missing');
    main.scrollTop = main.scrollHeight;
    return {
      viewport: window.innerHeight,
      documentHeight: document.documentElement.scrollHeight,
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
      windowScroll: window.scrollY,
      bottomGap: main.getBoundingClientRect().bottom - journal.getBoundingClientRect().bottom,
      sidebarBottom: sidebar?.getBoundingClientRect().bottom,
      sidebarVisible: sidebar ? getComputedStyle(sidebar).display !== 'none' : false,
    };
  });
  expect(metrics.documentHeight).toBeLessThanOrEqual(metrics.viewport + 2);
  expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth + 2);
  expect(metrics.windowScroll).toBe(0);
  expect(metrics.bottomGap).toBeGreaterThanOrEqual(0);
  expect(metrics.bottomGap).toBeLessThan(100);
  if (metrics.sidebarVisible) expect(metrics.sidebarBottom).toBeCloseTo(metrics.viewport, 0);
}

test('Import upload, switch, dry-run and result keep scroll inside AppShell', async ({ page }) => {
  await page.goto('/admin/import');
  await page.locator('input[type="file"]').setInputFiles(resolve(process.cwd(), '../docs/import-example-20.xlsx'));
  await page.getByTestId('sheet-select').selectOption('ВУЗы');
  await expect(page.getByRole('heading', { name: 'Предпросмотр листа' })).toBeVisible();

  for (const width of [1440, 1024, 768, 390, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    const updateExisting = page.getByRole('switch', { name: 'Обновлять существующие записи' });
    await updateExisting.locator('..').click();
    await expect(updateExisting).not.toBeChecked();
    await expectImportScrollEndsAtContent(page);
    await updateExisting.locator('..').click();
    await expect(updateExisting).toBeChecked();
    await expectImportScrollEndsAtContent(page);
  }

  await page.getByRole('button', { name: 'Запустить dry-run' }).click();
  await expect(page.getByText('Проверочный запуск завершён')).toBeVisible({ timeout: 30_000 });
  await expectImportScrollEndsAtContent(page);
  await page.getByTestId('import-confirm').click();
  await expect(page.getByText('Импорт завершён')).toBeVisible({ timeout: 30_000 });
  await expectImportScrollEndsAtContent(page);
});

test('long pages retain one AppShell scroll container', async ({ page }) => {
  for (const path of ['/reports', '/audit', '/universities/university-014', '/workflows/university-014']) {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(path);
      await expect(page.locator('main')).not.toContainText('Ошибка сервера');
      const metrics = await page.evaluate(() => {
        const main = document.querySelector('main');
        const sidebar = document.querySelector('aside');
        if (!main) throw new Error('AppShell main is missing');
        return {
          documentHeight: document.documentElement.scrollHeight,
          viewportHeight: innerHeight,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
          sidebarBottom: sidebar?.getBoundingClientRect().bottom,
          sidebarVisible: sidebar ? getComputedStyle(sidebar).display !== 'none' : false,
        };
      });
      expect(metrics.documentHeight).toBeLessThanOrEqual(metrics.viewportHeight + 2);
      expect(metrics.documentWidth).toBeLessThanOrEqual(metrics.viewportWidth + 2);
      if (metrics.sidebarVisible) expect(metrics.sidebarBottom).toBeCloseTo(metrics.viewportHeight, 0);
    }
  }
});
