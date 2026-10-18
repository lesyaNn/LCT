"""Execute the OAuth callback JavaScript, including failure paths, in Node."""

import json
import re
import shutil
import subprocess

import pytest

from app.core.swagger import OAUTH2_REDIRECT_HTML


@pytest.mark.skipif(not shutil.which("node"), reason="Node is required to execute browser JS")
@pytest.mark.parametrize("query,opener,success", [
    ("?code=valid%2Bcode%3D&state=expected", True, True),
    ("?code=valid&state=wrong", True, False),
    ("?code=valid", True, False),
    ("?error=access_denied&state=expected", True, False),
    ("?state=expected", True, False),
    ("?code=valid&state=expected", False, False),
])
def test_callback_exchanges_only_a_code_bound_to_its_popup(query, opener, success):
    script = re.search(r"<script>(.*?)</script>", OAUTH2_REDIRECT_HTML, re.S).group(1)
    harness = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
const callbacks = [], errors = [], status = {};
let closed = false;
const oauth = {state: 'expected', redirectUrl: 'https://crm.example/backend/docs/oauth2-redirect.html',
  auth: {name: 'KeycloakLogin'}, callback: value => callbacks.push(value),
  errCb: value => errors.push(value)};
vm.runInNewContext(input.script, {URLSearchParams,
  window: {opener: input.opener ? {swaggerUIRedirectOauth2: oauth} : null,
           location: {search: input.query}, close: () => {closed = true;}},
  document: {readyState: 'complete', getElementById: () => status}});
if (input.success) {
  assert.equal(callbacks.length, 1);
  assert.equal(callbacks[0].auth.code, 'valid+code=');
  assert.equal(callbacks[0].redirectUrl, oauth.redirectUrl);
  assert.equal(oauth.state, undefined);
  assert.equal(errors.length, 0);
  assert.equal(closed, true);
} else {
  assert.equal(callbacks.length, 0);
  assert.equal(oauth.auth.code, undefined);
  assert.equal(input.opener ? errors.length : Boolean(status.textContent), input.opener ? 1 : true);
}
"""
    subprocess.run(
        ["node", "-e", harness], check=True, capture_output=True, text=True,
        input=json.dumps({"script": script, "query": query, "opener": opener, "success": success}),
    )
