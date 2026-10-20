import { createServer } from 'node:http';
import { expect, test } from '@playwright/test';

test('same-origin assistant response survives longer than the old 30-second proxy limit', async ({ request }) => {
  test.skip(process.env.E2E_ASSISTANT_PROXY_TEST !== '1', 'Build the isolated frontend with API_PROXY_TARGET=http://127.0.0.1:3318 first.');
  const server = createServer((incoming, response) => {
    if (incoming.url !== '/api/v1/assistant/chat' || incoming.method !== 'POST' || incoming.headers.authorization !== 'Bearer synthetic-proxy-test') {
      response.writeHead(404).end();
      return;
    }
    incoming.resume();
    setTimeout(() => {
      response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({ answer: 'Уточните, на каком шаге возник вопрос.', model: 'local-test' }));
    }, 31_000);
  });
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject);
    server.listen(3318, '127.0.0.1', resolve);
  });
  try {
    const started = Date.now();
    const response = await request.post('/api/v1/assistant/chat', { headers: { Authorization: 'Bearer synthetic-proxy-test' }, data: { message: 'Проверка длинного ответа' }, timeout: 45_000 });
    expect(response.status()).toBe(200);
    expect((await response.json()).model).toBe('local-test');
    expect(Date.now() - started).toBeGreaterThanOrEqual(31_000);
  } finally {
    await new Promise<void>(resolve => server.close(() => resolve()));
  }
});
