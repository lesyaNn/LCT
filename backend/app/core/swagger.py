"""OAuth popup callback for Swagger's Authorization Code + PKCE flow."""

OAUTH2_REDIRECT_HTML = """<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Swagger: вход через Keycloak</title></head>
<body><p id="status">Завершаем вход…</p>
<script>
"use strict";
function run() {
    const oauth2 = window.opener && window.opener.swaggerUIRedirectOauth2;
    if (!oauth2) {
        document.getElementById("status").textContent =
            "Окно входа недействительно. Откройте Swagger и нажмите Authorize повторно.";
        return;
    }
    const params = new URLSearchParams(window.location.search);
    function fail(message) {
        oauth2.errCb({authId: oauth2.auth.name, source: "auth", level: "error", message});
        window.close();
    }
    // Reject the callback before exchanging any code when state is missing or different.
    if (!oauth2.state || params.get("state") !== oauth2.state) {
        fail("OAuth state не совпадает. Повторите вход через Authorize.");
        return;
    }
    if (params.has("error") || !params.get("code")) {
        fail("Keycloak не завершил вход: " + (params.get("error") || "нет authorization code"));
        return;
    }
    oauth2.auth.code = params.get("code");
    delete oauth2.state;
    // Swagger needs the original redirect URI again when exchanging the code for tokens.
    oauth2.callback({auth: oauth2.auth, redirectUrl: oauth2.redirectUrl});
    window.close();
}
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
} else {
    run();
}
</script></body></html>"""
