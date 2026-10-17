import { expect, test } from '@playwright/test';

const id = '149b29fb-c710-446a-9b3c-e8dbdc6c3a2a';
const path = `/verify/license/${id}`;
const response = {
  status: 'confirmed', status_label: 'Лицензия подтверждена',
  reason: 'Сведения подтверждены текущими данными CRM.',
  checked_at: '2026-10-17T12:30:00Z',
  university_name: 'Санкт-Петербургский государственный университет телекоммуникаций им. проф. М. А. Бонч-Бруевича',
  product_name: 'Платформа виртуальных лабораторий', license_number: 'ЛЦ-2026-0017',
  contract_number: 'РТК-2026/107', signed_at: '2026-09-15', expires_at: '2027-09-14',
};

test('public verification needs no login, refreshes status and handles network errors', async ({ page }) => {
  let state = 'confirmed';
  await page.route(`**/api/v1/public/licenses/${id}/verification`, (route) => state === 'offline'
    ? route.abort('failed')
    : route.fulfill({ json: { ...response, status: state,
      status_label: state === 'revoked' ? 'Лицензия недействительна' : response.status_label,
      reason: state === 'revoked' ? 'Договор прекращён.' : response.reason } }));
  await page.goto(path);
  await expect(page.getByRole('heading', { name: 'Проверка подлинности' })).toBeVisible();
  await expect(page.getByText('Лицензия подтверждена', { exact: true })).toBeVisible();
  await expect(page.getByText(response.university_name)).toBeVisible();
  await page.screenshot({ path: '../tmp/pdfs/license-verification-desktop.png', fullPage: true });
  state = 'revoked';
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  await expect(page.getByText('Договор прекращён.')).toBeVisible();
  await expect(page.getByText('Лицензия подтверждена', { exact: true })).toHaveCount(0);
  state = 'offline';
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  await expect(page.getByRole('heading', { name: 'Не удалось проверить лицензию' })).toBeVisible();
  await expect(page.getByText('Договор прекращён.')).toHaveCount(0);
});

test('mobile, unknown license, expired license and malformed URL', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let unknown = false;
  await page.route(`**/api/v1/public/licenses/${id}/verification`, (route) => route.fulfill({ json: unknown
    ? { ...response, status: 'invalid', status_label: 'Лицензия не найдена', university_name: null }
    : { ...response, status: 'expired', status_label: 'Срок действия истёк' } }));
  await page.goto(path);
  await expect(page.getByText('Срок действия истёк', { exact: true })).toBeVisible();
  await expect(page.getByText(response.university_name)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../tmp/pdfs/license-verification-mobile.png', fullPage: true });
  unknown = true;
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  await expect(page.getByText('Лицензия не найдена', { exact: true })).toBeVisible();
  await expect(page.getByText(response.university_name)).toHaveCount(0);
  await page.goto('/verify/license/unknown');
  await expect(page.getByRole('alert').filter({ hasText: 'Некорректная ссылка проверки' })).toBeVisible();
});
