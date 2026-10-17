import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { expect, test, type Page } from '@playwright/test';
import type { AssistantChatReply, AssistantQuickReplies, AssistantTurn } from '../shared/lib/assistant-repository';

test.use({ launchOptions: process.env.E2E_CHROMIUM_PATH ? { executablePath: process.env.E2E_CHROMIUM_PATH } : {} });
type Fixture = { catalog: AssistantQuickReplies; replies: Record<string, AssistantChatReply> };
let fixture: Fixture;
test.beforeAll(() => {
  test.skip(!process.env.E2E_ASSISTANT_PYTHON, 'Set E2E_ASSISTANT_PYTHON to a backend Python environment.');
  const code = `
import json
from unittest.mock import Mock
from uuid import uuid4
from app.config import Settings
from app.core.security import CurrentUser
from app.modules.assistant.quick_replies import QUICK_REPLIES
from app.modules.assistant.router import quick_replies
from app.modules.assistant.repository import Prepared
from app.modules.assistant.schemas import ChatIn
from app.modules.assistant.service import Assistant
provider, knowledge, repository = Mock(), Mock(), Mock()
repository.prepare.return_value = Prepared(uuid4(), 0, (), True)
repository.save.side_effect = lambda prepared, question, result: result
assistant = Assistant(Settings(assistant_enabled=True), knowledge, provider)
replies = {reply.question: assistant.chat(ChatIn(message=reply.question), 'user', repository).model_dump(mode='json') for reply in QUICK_REPLIES}
assert provider.mock_calls == [] and knowledge.mock_calls == []
print(json.dumps({'catalog': quick_replies(CurrentUser(id='test', roles={'user'})).model_dump(), 'replies': replies}, ensure_ascii=False))
`;
  fixture = JSON.parse(execFileSync(process.env.E2E_ASSISTANT_PYTHON!, ['-B', '-c', code], {
    cwd: path.resolve(process.cwd(), '../backend'), encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  }));
});

async function session(page: Page, failCatalog = false) {
  const conversationId = crypto.randomUUID();
  const history: AssistantTurn[] = [];
  const requests: Array<{ message: string; conversation_id?: string; expected_revision?: number }> = [];
  const errors: string[] = [];
  let catalogCalls = 0;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/realms/rtk/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/3p-cookies/step1.html')) await route.fulfill({ contentType: 'text/html', body: '<script>parent.postMessage("supported", "*")</script>' });
    else if (url.pathname.endsWith('/auth')) {
      const redirect = new URL(url.searchParams.get('redirect_uri')!);
      redirect.hash = new URLSearchParams({ state: url.searchParams.get('state')!, session_state: 'test', code: url.searchParams.get('nonce')! }).toString();
      await route.fulfill({ status: 302, headers: { location: redirect.toString() } });
    } else if (url.pathname.endsWith('/token')) {
      const part = (value: unknown) => Buffer.from(JSON.stringify(value)).toString('base64url');
      const token = `${part({ alg: 'RS256' })}.${part({ sub: 'quick-test', nonce: new URLSearchParams(route.request().postData() ?? '').get('code'), exp: Math.floor(Date.now() / 1000) + 3600, iat: Math.floor(Date.now() / 1000), realm_access: { roles: ['user'] }, aud: 'rtk-api' })}.signature`;
      await route.fulfill({ contentType: 'application/json', headers: {
        'Access-Control-Allow-Origin': new URL(process.env.E2E_BASE_URL || 'http://localhost:3000').origin, 'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Methods': 'POST, OPTIONS',
      }, body: JSON.stringify({ access_token: token, id_token: token, refresh_token: token, token_type: 'Bearer', expires_in: 3600 }) });
    } else await route.abort();
  });
  await page.route('**/api/v1/**', async route => {
    const pathname = new URL(route.request().url()).pathname;
    let body: unknown = {};
    if (pathname.endsWith('/auth/me')) body = { id: 'quick-test', username: 'reader', name: 'Тест', roles: ['user'], permissions: ['assistant.use', 'university.read'] };
    if (pathname.endsWith('/unread-count')) body = { count: 0 };
    if (pathname.endsWith('/assistant/quick-replies')) {
      catalogCalls += 1;
      if (failCatalog && catalogCalls <= 4) { await route.fulfill({ status: 503, body: '{}' }); return; }
      body = fixture.catalog;
    }
    if (pathname.endsWith('/assistant/conversations')) body = { items: history.length ? [{ id: conversationId, revision: history.length }] : [], total: history.length ? 1 : 0 };
    if (pathname.endsWith(`/assistant/conversations/${conversationId}`)) body = { conversation: { id: conversationId, revision: history.length }, items: history, total: history.length };
    if (pathname.endsWith('/assistant/chat')) {
      const request = route.request().postDataJSON();
      requests.push(request);
      const reply = fixture.replies[request.message];
      if (!reply) { await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'ASSISTANT_UNAVAILABLE', message: 'Unavailable' } }) }); return; }
      const turn = { ...reply, question: request.message, conversation_id: conversationId, turn_id: crypto.randomUUID(), revision: history.length + 1 };
      history.push(turn);
      body = turn;
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
  });
  return { requests, errors };
}

async function open(page: Page) {
  await page.goto('/docs?article=user-guide%2Fgetting-started');
  await page.getByRole('button', { name: 'Открыть ИИ-помощника', exact: true }).click();
  return page.getByRole('dialog', { name: 'ИИ-помощник' });
}

test('status clarification and not-helpful feedback stay correct after a report answer and page reload', async ({ page }, testInfo) => {
  const checks = await session(page);
  let dialog = await open(page);
  const menu = dialog.locator('[aria-label="Быстрые вопросы"]');
  await menu.getByRole('button', { name: 'Как скачать отчёт?', exact: true }).click();
  await expect(dialog.getByText(fixture.replies['Как скачать отчёт?'].answer, { exact: true })).toBeVisible();
  await menu.getByRole('button', { name: 'Что означает статус?', exact: true }).click();
  await expect(dialog.getByText(fixture.replies['Что означает статус?'].answer, { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Ответ не подходит', exact: true }).click();
  await expect(dialog.getByText(fixture.replies['Ответ не подходит'].answer, { exact: true })).toBeVisible();
  expect(checks.requests.map(request => request.message)).toEqual(['Как скачать отчёт?', 'Что означает статус?', 'Ответ не подходит']);
  expect(checks.requests[1].expected_revision).toBe(1);
  expect(checks.requests[2].expected_revision).toBe(2);
  await page.reload();
  await page.getByRole('button', { name: 'Открыть ИИ-помощника', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'ИИ-помощник' });
  await expect(dialog.getByText(fixture.replies['Что означает статус?'].answer, { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Все быстрые вопросы' }).click();
  await expect(dialog.locator('[aria-label="Быстрые вопросы"]').getByRole('button')).toHaveCount(10);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => dialog.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('assistant-quick-mobile.png'), fullPage: true });
  expect(checks.errors).toEqual([]);
});

test('failed catalog can be retried while regular questions remain available', async ({ page }) => {
  const checks = await session(page, true);
  const dialog = await open(page);
  await expect(dialog.getByText('Быстрые вопросы недоступны.', { exact: false })).toBeVisible({ timeout: 20000 });
  await expect(dialog.getByLabel('Напишите вопрос', { exact: true })).toBeEnabled();
  await dialog.getByRole('button', { name: 'Загрузить снова' }).click();
  await expect(dialog.getByRole('button', { name: 'Что означает статус?', exact: true })).toBeVisible();
  await dialog.getByLabel('Напишите вопрос', { exact: true }).fill('Где найти контакты вуза?');
  await dialog.getByRole('button', { name: 'Отправить вопрос', exact: true }).click();
  await expect(dialog.getByText(fixture.replies['Где найти контакты вуза?'].answer, { exact: true })).toBeVisible();
  expect(checks.errors).toEqual([]);
});
