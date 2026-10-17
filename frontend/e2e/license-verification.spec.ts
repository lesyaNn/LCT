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
  await expect(page.getByRole('img', { name: 'Зелёная печать «Лицензия подтверждена»' })).toBeVisible();
  await expect(page.getByText('Лицензия подтверждена', { exact: true })).toHaveCount(0);
  await expect(page.getByText(response.university_name)).toBeVisible();
  await page.screenshot({ path: '../tmp/pdfs/license-verification-desktop.png', fullPage: true });
  state = 'revoked';
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  await expect(page.getByText('Договор прекращён.')).toBeVisible();
  await expect(page.getByText('Лицензия подтверждена', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Зелёная печать «Лицензия подтверждена»' })).toHaveCount(0);
  state = 'offline';
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  await expect(page.getByRole('heading', { name: 'Не удалось проверить лицензию' })).toBeVisible();
  await expect(page.getByText('Договор прекращён.')).toHaveCount(0);
  await expect(page.getByRole('img', { name: 'Зелёная печать «Лицензия подтверждена»' })).toHaveCount(0);
});

test.describe('confirmation stamp', () => {
  test.beforeEach(async ({ page }) => {
    // Observe real Web Animations calls before the page code starts.
    await page.addInitScript(() => {
      const original = Element.prototype.animate;
      const history: { duration: number; compressed: boolean }[] = [];
      (window as unknown as { stampAnimations: typeof history }).stampAnimations = history;
      Element.prototype.animate = function (frames, options) {
        if (this.querySelector('img[src="/brand/license-confirmed-stamp.png"]')) {
          const duration = typeof options === 'number' ? options : Number(options?.duration);
          const compressed = Array.isArray(frames) && frames.some((frame) => {
            const scale = /scale\(([\d.]+)\)/.exec(String(frame.transform));
            return scale && Number(scale[1]) >= .94 && Number(scale[1]) <= .96;
          });
          history.push({ duration, compressed });
        }
        return original.call(this, frames, options);
      };
    });
    await page.route(`**/api/v1/public/licenses/${id}/verification`, (route) => route.fulfill({ json: response }));
  });

  test('plays once per open page, stays still after refresh and plays on a new opening', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.goto(path);
    const stamp = page.getByRole('img', { name: 'Зелёная печать «Лицензия подтверждена»' });
    await expect(stamp).toBeVisible();
    await expect.poll(() => page.evaluate(() => (window as unknown as { stampAnimations: unknown[] }).stampAnimations.length)).toBe(1);
    const [animation] = await page.evaluate(() => (window as unknown as { stampAnimations: { duration: number; compressed: boolean }[] }).stampAnimations);
    expect(animation.duration).toBeGreaterThanOrEqual(500);
    expect(animation.duration).toBeLessThanOrEqual(650);
    expect(animation.compressed).toBe(true);
    await expect.poll(() => stamp.evaluate((image) => image.parentElement!.getAnimations().filter((item) => item.playState === 'running').length)).toBe(0);
    await expect(stamp.locator('..')).toHaveCSS('opacity', '1');
    await expect(stamp.locator('..')).toHaveCSS('transform', 'none');
    const facts = page.getByRole('region', { name: 'Сведения о лицензии' });
    await expect(facts.getByRole('img', { name: 'Зелёная печать «Лицензия подтверждена»' })).toBeVisible();
    expect(await stamp.locator('../..').evaluate((element) => getComputedStyle(element).transform)).not.toBe('none');
    const sealBox = await stamp.locator('../..').boundingBox();
    const factsBox = await facts.boundingBox();
    expect(Math.abs((sealBox!.y + sealBox!.height / 2) - (factsBox!.y + factsBox!.height / 2))).toBeLessThan(1);
    const contractBox = await facts.getByText(response.contract_number, { exact: true }).boundingBox();
    expect(sealBox!.y).toBeLessThan(contractBox!.y);
    expect(contractBox!.x + contractBox!.width).toBeLessThan(sealBox!.x);
    await page.screenshot({ path: '../tmp/pdfs/license-verification-stamp-desktop.png', fullPage: true });
    await page.getByRole('button', { name: 'Проверить снова' }).click();
    await expect(stamp).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { stampAnimations: unknown[] }).stampAnimations.length)).toBe(1);
    await page.reload();
    await expect.poll(() => page.evaluate(() => (window as unknown as { stampAnimations: unknown[] }).stampAnimations.length)).toBe(1);
  });

  test('reduced motion shows a static stamp on mobile without any animation', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    const stamp = page.getByRole('img', { name: 'Зелёная печать «Лицензия подтверждена»' });
    await expect(stamp).toBeVisible();
    await expect.poll(() => stamp.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBe(1536);
    await expect(stamp.locator('..')).toHaveCSS('opacity', '1');
    await expect(stamp.locator('..')).toHaveCSS('transform', 'none');
    expect(await page.evaluate(() => (window as unknown as { stampAnimations: unknown[] }).stampAnimations.length)).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    await page.screenshot({ path: '../tmp/pdfs/license-verification-stamp-mobile.png', fullPage: true });
  });
});

test('mobile, unknown license, expired license and malformed URL', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let unknown = false;
  await page.route(`**/api/v1/public/licenses/${id}/verification`, (route) => route.fulfill({ json: unknown
    ? { ...response, status: 'invalid', status_label: 'Лицензия не найдена', university_name: null,
      product_name: null, license_number: null, contract_number: null, signed_at: null, expires_at: null,
      reason: 'Проверьте ссылку или обратитесь к выдавшей документ организации.' }
    : { ...response, status: 'expired', status_label: 'Срок действия истёк' } }));
  await page.goto(path);
  await expect(page.getByText('Срок действия истёк', { exact: true })).toHaveCount(0);
  await expect(page.getByText(response.university_name)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: '../tmp/pdfs/license-verification-mobile.png', fullPage: true });
  unknown = true;
  await page.getByRole('button', { name: 'Проверить снова' }).click();
  const missingStamp = page.getByRole('img', { name: 'Красная печать «Лицензия не найдена»' });
  await expect(missingStamp).toBeVisible();
  await expect.poll(() => missingStamp.evaluate((image) => (image as HTMLImageElement).naturalWidth)).toBe(1536);
  await expect.poll(() => missingStamp.evaluate((image) => image.parentElement!.getAnimations().filter((item) => item.playState === 'running').length)).toBe(0);
  await expect(page.getByText('Лицензия не найдена', { exact: true })).toHaveCount(0);
  const explanation = page.getByText('В реестре нет записи об этой лицензии.', { exact: true });
  await expect(explanation).toBeVisible();
  await page.screenshot({ path: '../tmp/pdfs/license-verification-not-found-stamp-mobile.png', fullPage: true });
  await page.setViewportSize({ width: 1440, height: 900 });
  const explanationBox = await explanation.boundingBox();
  const stampBox = await missingStamp.locator('../..').boundingBox();
  expect(explanationBox!.x + explanationBox!.width).toBeLessThan(stampBox!.x);
  await page.screenshot({ path: '../tmp/pdfs/license-verification-not-found-stamp-desktop.png', fullPage: true });
  await expect(page.getByText(response.university_name)).toHaveCount(0);
  await page.goto('/verify/license/unknown');
  await expect(page.getByRole('alert').filter({ hasText: 'Некорректная ссылка проверки' })).toBeVisible();
});
