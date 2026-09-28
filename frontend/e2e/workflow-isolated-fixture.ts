import { expect, type APIRequestContext, type Page } from '@playwright/test';

const apiBase = process.env.E2E_API_URL ?? 'http://localhost:8000';

export function requireIsolatedWorkflowStand(): void {
  expect(process.env.E2E_DISPOSABLE_DB, 'Mutating Workflow E2E requires a disposable database.').toBe('1');
  expect(process.env.E2E_WORKFLOW_UNIVERSITY_ID, 'Set the disposable stand university ID.').toBeTruthy();
}

export async function loginForWorkflowE2E(page: Page): Promise<string> {
  let authorization = '';
  page.on('request', (request) => {
    if (request.url().includes('/api/v1/auth/me')) authorization = request.headers().authorization ?? authorization;
  });
  await page.goto('/login');
  const keycloakButton = page.getByRole('button', { name: 'Войти через Keycloak' });
  if (await keycloakButton.isVisible().catch(() => false)) await keycloakButton.click();
  await page.locator('input[name="username"]').fill(process.env.E2E_ADMIN_USERNAME ?? '');
  await page.locator('input[name="password"]').fill(process.env.E2E_ADMIN_PASSWORD ?? '');
  await page.getByRole('button', { name: /Вход|Войти|Sign in|Log in/i }).click();
  await page.waitForURL((url) => url.pathname === '/dashboard');
  await expect.poll(() => authorization).toMatch(/^Bearer /);
  return authorization;
}

export async function createIsolatedWorkflow(request: APIRequestContext, authorization: string, templateNameIncludes?: string): Promise<string> {
  requireIsolatedWorkflowStand();
  const headers = { authorization };
  const get = async (path: string) => {
    const response = await request.get(`${apiBase}/api/v1${path}`, { headers });
    expect(response.status(), `${path}: ${await response.text()}`).toBe(200);
    return response.json() as Promise<Record<string, unknown>>;
  };
  const post = async (path: string, data: Record<string, unknown>) => {
    const response = await request.post(`${apiBase}/api/v1${path}`, { headers, data });
    expect(response.status(), `${path}: ${await response.text()}`).toBe(201);
    return response.json() as Promise<Record<string, unknown>>;
  };
  const direction = (await get('/directions?page=1&page_size=1')).items as Array<{ id: string }>;
  const templates = (await get('/workflow/templates?page=1&page_size=100')).items as Array<{ id: string; name: string; is_active: boolean }>;
  const template = templates.find((item) => item.is_active && (!templateNameIncludes || item.name.includes(templateNameIncludes)));
  expect(direction[0]?.id).toBeTruthy();
  expect(template?.id).toBeTruthy();
  const program = await post('/programs', { direction_id: direction[0].id, name: `Workflow E2E ${crypto.randomUUID()}` });
  const universityId = process.env.E2E_WORKFLOW_UNIVERSITY_ID!;
  await post(`/universities/${universityId}/programs`, { program_id: program.id });
  const instance = await post('/workflow/instances', { university_id: universityId, program_id: program.id, template_id: template!.id });
  return String(instance.id);
}

export function validTestPdf(label: string): Buffer {
  const content = `BT /F1 12 Tf 36 72 Td (${label.replace(/[^a-zA-Z0-9 ]/g, '')}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 120] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}\nendstream`,
  ];
  let pdf = '%PDF-1.4\n';
  const offsets = [0];
  for (let i = 0; i < objects.length; i += 1) {
    offsets.push(Buffer.byteLength(pdf));
    pdf += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(pdf);
  pdf += `xref\n0 ${offsets.length}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) pdf += `${String(offset).padStart(10, '0')} 00000 n \n`;
  pdf += `trailer\n<< /Size ${offsets.length} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;
  return Buffer.from(pdf);
}
