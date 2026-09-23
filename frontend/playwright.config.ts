import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.E2E_BASE_URL?.trim() || 'http://localhost:3000';

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  globalTimeout: 5 * 60_000,
  timeout: 4 * 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [
    ['line'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],
  use: {
    baseURL,
    headless: true,
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
});
