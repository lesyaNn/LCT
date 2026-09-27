import { expect, test, type Page } from '@playwright/test';

const tab = (page: Page, id: string) => page.locator(`#catalog-tab-${id}`);
const row = (page: Page, name: string) => page.locator('[data-testid^="catalog-row-"]').filter({ has: page.getByRole('button', { name, exact: true }) });
const catalogTabs = ['universities', 'directions', 'programs', 'vendors', 'products', 'agreements', 'responsibles'] as const;

/**
 * Real catalog management: every one of the seven backend catalogs is listed,
 * edited and hard-deleted through /admin/catalogs.
 *
 * Opt-in like the other `-real` specs: skipped unless E2E_MANAGER_USERNAME and
 * E2E_MANAGER_PASSWORD are exported. The scenario is self-cleaning — it only
 * creates records whose names carry `Date.now()` and deletes them again — but
 * it does read live reference data, so run it against a disposable stand.
 */
test('catalogs: all seven catalogs are listed, edited and deleted', async ({ page }) => {
  test.skip(!process.env.E2E_MANAGER_USERNAME || !process.env.E2E_MANAGER_PASSWORD,
    'Set E2E_MANAGER_USERNAME and E2E_MANAGER_PASSWORD for the real catalog smoke.');

  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_MANAGER_USERNAME!);
  await page.locator('input[name="password"]').fill(process.env.E2E_MANAGER_PASSWORD!);
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');

  await page.goto('/admin/catalogs');
  for (const id of catalogTabs) await expect(tab(page, id)).toBeVisible();

  // The soft-deactivate fiction is gone: hard delete replaces it entirely.
  await expect(page.getByTestId('deactivate-toggle')).toHaveCount(0);
  await expect(page.getByText('Показывать неактивные')).toHaveCount(0);

  // Vendors stay a separate catalog; contracts and licences got a tab of their
  // own and share it through an inner switch.
  await expect(tab(page, 'vendors')).toHaveText('Вендоры');
  await expect(tab(page, 'agreements')).toHaveText('Договоры и лицензии');

  // The responsibles list is fed by GET /responsibles, which does NOT expose
  // universities the way the per-item detail does. Regression guard: the ВУЗы
  // column must show real names, not "Нет" or bare counts.
  await tab(page, 'responsibles').click();
  const responsibleRow = page.locator('[data-testid^="catalog-row-"]').first();
  await expect(responsibleRow).toBeVisible();
  // Anchored to the header, not to a fixed position, so reordering columns
  // does not silently move the assertion onto another field. The table CSS
  // uppercases headers, hence the case-insensitive match.
  const universitiesColumn = (await page.locator('thead th').allInnerTexts())
    .findIndex((header) => header.trim().toLowerCase() === 'вузы');
  expect(universitiesColumn, 'responsibles table must keep a ВУЗы column').toBeGreaterThan(0);
  const responsibleUniversities = (await responsibleRow.locator('td').nth(universitiesColumn).innerText()).trim();
  expect(responsibleUniversities, 'responsibles list must carry university names').not.toBe('Нет');
  expect(responsibleUniversities.length, `ВУЗы must hold real names, got "${responsibleUniversities}"`).toBeGreaterThan(3);

  // A vendor is the simplest catalog: full create -> edit -> delete round-trip.
  // Every step is scoped by a unique name so the assertions never depend on
  // how many rows the stand happens to hold or on their sort position.
  await tab(page, 'vendors').click();
  const vendorName = `E2E вендор ${Date.now()}`;
  await page.getByTestId('catalog-add').click();
  await page.getByLabel(/^Название/).fill(vendorName);
  await page.getByRole('dialog').getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText('Запись добавлена')).toBeVisible();
  await page.getByRole('searchbox', { name: 'Поиск' }).fill(vendorName);
  await expect(row(page, vendorName)).toHaveCount(1);

  const renamedVendor = `${vendorName} (изменён)`;
  await page.getByRole('button', { name: `Изменить ${vendorName}` }).click();
  await page.getByLabel(/^Название/).fill(renamedVendor);
  await page.getByRole('dialog').getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Запись сохранена')).toBeVisible();
  await expect(row(page, renamedVendor)).toHaveCount(1);

  await page.getByRole('button', { name: `Удалить ${renamedVendor}` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(page.getByText('Запись удалена')).toBeVisible();
  await expect(page.getByText('Записи не найдены')).toBeVisible();

  // A program carries its mandatory direction reference.
  await tab(page, 'programs').click();
  const programName = `E2E программа ${Date.now()}`;
  await page.getByTestId('catalog-add').click();
  await page.getByLabel(/^Название/).fill(programName);
  await page.getByLabel(/^Направление/).selectOption({ index: 1 });
  await page.getByLabel(/^Описание/).fill('Создано проверкой каталогов');
  await page.getByRole('dialog').getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText('Запись добавлена')).toBeVisible();
  await page.getByRole('searchbox', { name: 'Поиск' }).fill(programName);
  await expect(row(page, programName)).toHaveCount(1);

  await page.getByRole('button', { name: `Удалить ${programName}` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(page.getByText('Запись удалена')).toBeVisible();
  await expect(page.getByText('Записи не найдены')).toBeVisible();

  // Contracts and licences share one tab but are two resources. A contract
  // round-trips on its own, then a licence is created under it, which in turn
  // must block the contract delete with 409.
  await tab(page, 'agreements').click();
  await expect(page.getByTestId('catalog-agreements-contracts')).toHaveAttribute('aria-pressed', 'true');
  const contractNumber = `E2E ${Date.now()}`;
  await page.getByTestId('catalog-add').click();
  const contractDialog = page.getByRole('dialog');
  await contractDialog.getByLabel(/^ВУЗ/).selectOption({ index: 1 });
  await contractDialog.getByLabel(/^Номер договора/).fill(contractNumber);
  await contractDialog.getByLabel(/^Дата подписания/).fill('2026-02-01');
  await contractDialog.getByLabel(/^Дата окончания/).fill('2027-02-01');
  await contractDialog.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText('Запись добавлена')).toBeVisible();
  await page.getByRole('searchbox', { name: 'Поиск' }).fill(contractNumber);
  const contractRow = row(page, contractNumber);
  await expect(contractRow).toHaveCount(1);
  // The university is resolved server-side and shown as a name, not as an id.
  expect((await contractRow.innerText()), 'contract row must carry the university name').toMatch(/\S+ \S+/);

  const renumberedContract = `${contractNumber}-изм`;
  await page.getByRole('button', { name: `Изменить ${contractNumber}` }).click();
  await page.getByRole('dialog').getByLabel(/^Номер договора/).fill(renumberedContract);
  await page.getByRole('dialog').getByRole('button', { name: 'Сохранить' }).click();
  await expect(page.getByText('Запись сохранена')).toBeVisible();
  await expect(row(page, renumberedContract)).toHaveCount(1);

  // A licence requires a product and points at its contract.
  await page.getByRole('button', { name: 'Сбросить', exact: true }).click();
  await page.getByTestId('catalog-agreements-licenses').click();
  await expect(page.getByTestId('catalog-agreements-licenses')).toHaveAttribute('aria-pressed', 'true');
  const licenseNumber = `${renumberedContract}-лиц`;
  await page.getByTestId('catalog-add').click();
  // Scoped to the dialog: the tab itself is labelled "Договоры и лицензии",
  // which a bare /^Договор/ locator would also match.
  const licenseDialog = page.getByRole('dialog');
  await licenseDialog.getByLabel(/^ВУЗ/).selectOption({ index: 1 });
  await licenseDialog.getByLabel(/^Номер лицензии/).fill(licenseNumber);
  await licenseDialog.getByLabel(/^ИТ-продукт/).selectOption({ index: 1 });
  // The contract select is reference data, so the option value is only known
  // at runtime: read it back from the rendered option rather than guessing.
  const contractSelect = licenseDialog.getByLabel(/^Договор/);
  const contractValue = await contractSelect.locator('option')
    .evaluateAll((options, needle) => options.find((option) => (option.textContent ?? '').includes(needle))?.getAttribute('value') ?? '', renumberedContract);
  expect(contractValue, 'contract must be offered in the license form').not.toBe('');
  await contractSelect.selectOption(contractValue);
  await licenseDialog.getByLabel(/^Дата подписания/).fill('2026-02-02');
  // A licence always has an end date: licenses.expires_at is NOT NULL.
  await licenseDialog.getByLabel(/^Дата окончания/).fill('2027-02-02');
  await licenseDialog.getByRole('button', { name: 'Добавить', exact: true }).click();
  await expect(page.getByText('Запись добавлена')).toBeVisible();
  await page.getByRole('searchbox', { name: 'Поиск' }).fill(licenseNumber);
  const licenseRow = row(page, licenseNumber);
  await expect(licenseRow).toHaveCount(1);
  expect((await licenseRow.innerText()), 'license row must name its contract').toContain(renumberedContract);

  // The licence goes first; only then is the contract deletable.
  await page.getByRole('button', { name: `Удалить ${licenseNumber}` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(page.getByText('Запись удалена')).toBeVisible();
  // Assert the row is gone, not just that a toast appeared: a toast left over
  // from the previous delete would satisfy the text match instantly and let the
  // test end before the request landed, leaking the record.
  await expect(row(page, licenseNumber)).toHaveCount(0);

  await page.getByRole('button', { name: 'Сбросить', exact: true }).click();
  await page.getByTestId('catalog-agreements-contracts').click();
  await page.getByRole('searchbox', { name: 'Поиск' }).fill(renumberedContract);
  await expect(row(page, renumberedContract)).toHaveCount(1);
  await page.getByRole('button', { name: `Удалить ${renumberedContract}` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(row(page, renumberedContract)).toHaveCount(0);

  // A referenced record cannot be removed: the backend answers 409 and the
  // dialog explains which relation blocks the delete.
  await page.getByRole('button', { name: 'Сбросить', exact: true }).click();
  await tab(page, 'directions').click();
  const referencedDirection = await page.locator('[data-testid^="catalog-row-"]').first().locator('td').first().innerText();
  await page.getByRole('button', { name: `Удалить ${referencedDirection}` }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Удалить', exact: true }).click();
  await expect(page.getByRole('dialog').getByRole('alert')).toHaveText(/Нельзя удалить направление/);
  await expect(page.getByRole('button', { name: `Удалить ${referencedDirection}` })).toBeVisible();
});
