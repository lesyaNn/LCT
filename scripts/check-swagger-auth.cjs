const { chromium, expect } = require('../frontend/node_modules/@playwright/test');
const assert = require('node:assert/strict');
const base = (process.env.SWAGGER_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
(async () => {
  const browser = await chromium.launch({headless: true});
  const context = await browser.newContext({viewport:{width:1440,height:1100}});
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', e => {errors.push(e.message); console.error('PAGE_ERROR',e.message);});

  try {
    await page.goto(base + '/docs');
    await expect(page.locator('.swagger-ui .info .title')).toContainText('CRM');
    await page.locator('.auth-wrapper .authorize').click();
    const [popup] = await Promise.all([
      context.waitForEvent('page'),
      page.locator('.dialog-ux button.authorize').nth(1).click(),
    ]);
    await popup.locator('#username').waitFor();
    const authUrl = new URL(popup.url());
    assert.equal(authUrl.searchParams.get('code_challenge_method'), 'S256');
    assert.equal(authUrl.searchParams.get('redirect_uri'), base + '/docs/oauth2-redirect.html');
    assert.ok(authUrl.searchParams.get('scope').split(' ').includes('openid'));
    const tokenResponse = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/protocol/openid-connect/token') && r.request().method() === 'POST');
    await popup.locator('#username').fill(process.env.E2E_ADMIN_USERNAME || 'admin');
    await popup.locator('#password').fill(process.env.E2E_ADMIN_PASSWORD || 'admin123');
    await popup.locator('#kc-login').click();
    const response = await tokenResponse;
    assert.equal(response.status(), 200);
    const token = (await response.json()).access_token;
    assert.equal(typeof token, 'string');
    const exchange = new URLSearchParams(response.request().postData());
    assert.ok(exchange.get('code_verifier'));
    assert.equal(exchange.get('redirect_uri'), base + '/docs/oauth2-redirect.html');
    assert.ok(!exchange.get('client_secret'));
    await page.waitForFunction(() => ui.authSelectors.authorized().size > 0);
    await page.locator('.close-modal').click();
    async function executeMe() {
      const block = page.locator('.opblock').filter({has: page.locator('.opblock-summary-path').filter({hasText: /^\/api\/v1\/auth\/me$/})});
      if (!(await block.evaluate(e => e.classList.contains('is-open')))) {
        await block.locator('.opblock-summary').click();
      }
      if (!(await block.getByRole('button', {name: 'Execute', exact: true}).isVisible())) {
        await block.getByRole('button', {name: 'Try it out', exact: true}).click();
      }
      const resultReady = page.waitForResponse(r => r.url() === base + '/api/v1/auth/me');
      await block.getByRole('button', {name: 'Execute', exact: true}).click();
      return await resultReady;
    }
    let me = await executeMe();
    assert.equal(me.status(), 200);
    assert.ok((await me.json()).roles.includes('admin'));
    assert.ok(me.request().headers().authorization.startsWith('Bearer '));
    console.log('PASS Keycloak login: PKCE S256, code exchange, /auth/me=200, admin role');
    await page.reload();
    await expect(page.locator('.swagger-ui .info .title')).toContainText('CRM');
    assert.equal(await page.evaluate(() => ui.authSelectors.authorized().size), 0);
    await page.locator('.auth-wrapper .authorize').click();
    const bearer = page.locator('.auth-container').filter({has: page.locator('h4').filter({hasText: /^HTTPBearer/})});
    await bearer.locator('input').fill(token);
    await page.locator('.dialog-ux button.authorize').first().click();
    await page.waitForFunction(() => ui.authSelectors.authorized().size > 0);
    await page.locator('.close-modal').click();
    me = await executeMe();
    assert.equal(me.status(), 200);
    assert.ok(me.request().headers().authorization === 'Bearer ' + token, 'Bearer header differs from access token');
    console.log('PASS Bearer token: correct Authorization header, /auth/me=200');
    await page.reload();
    await expect(page.locator('.swagger-ui .info .title')).toContainText('CRM');
    assert.equal(await page.evaluate(() => ui.authSelectors.authorized().size), 0);
    const state = await context.storageState();
    assert.ok(!JSON.stringify(state).includes(token));
    me = await executeMe();
    assert.equal(me.status(), 401);
    assert.ok(!me.request().headers().authorization);
    console.log('PASS reload: tokens absent from persistent storage, anonymous /auth/me=401');
    assert.deepEqual(errors, []);
  } catch (e) {
    console.error('BROWSER_FAILURE', e.message);
    console.error('PAGE_TEXT', (await page.locator('body').innerText()).slice(-4500));
    process.exitCode = 1;
  } finally { await browser.close(); }
})();
