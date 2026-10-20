# Письма Keycloak

Тема `lct-crm` лежит в `keycloak/themes/lct-crm/email`. Она наследует `base` из Keycloak 26.7.4 и подключается существующим read-only volume `./keycloak/themes:/opt/keycloak/themes:ro`. Login theme `rostelecom` не меняется. Цвета взяты из frontend: фиолетовый `#7700FF`, тёмный текст `#101828`, светлый фон `#f4f4f7`. Шапка текстовая: письмо не зависит от загрузки внешней картинки.

Собственные HTML и text/plain шаблоны: `executeActions`, `password-reset`, `email-verification`. Общий `html/template.ftl` оформляет и остальные письма, унаследованные от `base`. Русские и английские темы сообщений находятся в `messages/`; тексты событий безопасности переопределены там без копирования шаблонов. Keycloak использует один `executeActionsSubject` для приглашения и последующих обязательных действий, поэтому заголовок нейтральный для обоих случаев.

## Локальная проверка

```powershell
python keycloak/check_email_theme.py
docker compose config --quiet
docker compose up -d --no-deps keycloak
docker compose ps keycloak
docker compose logs --tail=150 keycloak
```

В существующем realm импорт `realm-export.json` повторно не применяется. Выберите `lct-crm` в **Realm settings → Themes → Email theme** для `rtk` или обновите только поле `emailTheme` через Admin API. Для нового realm файл импорта уже выбирает `lct-crm`. Не изменяйте Login, Account и Admin themes.

## Публичные ссылки

`KEYCLOAK_EXTERNAL_URL` должен содержать **точный браузерный URL Keycloak** со схемой и путём, если у прокси есть префикс. Локальное значение — `http://localhost:8081`; на стенде оно должно совпадать с адресом, который использует frontend OIDC и через который Nginx Proxy Manager направляет запросы в Keycloak. Compose задаёт `KC_PROXY_HEADERS=xforwarded` по умолчанию; прокси должен выставлять `X-Forwarded-Proto` и `X-Forwarded-Host` (и префикс при необходимости). Прямой доступ к опубликованному порту Keycloak на публичном стенде следует закрыть на уровне сети, чтобы клиент не мог подменить эти заголовки. Не указывайте внутреннее имя сервиса в этой переменной. Тема берёт одноразовую ссылку из `link`, которую формирует Keycloak.

Проверьте публичный discovery endpoint `/realms/rtk/.well-known/openid-configuration`, затем отправьте приглашение, сброс пароля и подтверждение адреса **только в тестовый ящик**. Проверьте HTML, text/plain, отправителя и CTA в Gmail/Outlook. Откройте ссылку с внешнего компьютера и убедитесь, что её hostname публичный, действие открывается и URL не содержит внутренний hostname. Срок действия задаёт Keycloak; письма намеренно не называют фиксированное число часов.

SMTP realm настраивается отдельно; эта тема не меняет credentials и не затрагивает CRM Notification Service.
