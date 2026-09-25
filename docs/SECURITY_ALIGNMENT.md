# Security alignment прототипа

> **Это прототип. Он НЕ сертифицирован ФСТЭК. Этот документ НЕ является заключением о полном соответствии 152‑ФЗ.**
>
> Для промышленной эксплуатации нужны организационные меры, модель угроз,
> определение применимых требований, сертифицированные средства там, где они
> требуются, и юридическая/ИБ оценка.

Документ описывает фактические меры в текущем backend и их ограничения. Термины
«Implemented» и «Partial» относятся к коду этого репозитория и не являются
юридической классификацией системы.

## Области 152‑ФЗ

| Требование / область | Реализация в прототипе | Статус | Ограничения |
|---|---|---|---|
| Идентификация и аутентификация | Keycloak OIDC, JWT RS256, JWKS, issuer/audience/exp checks, BearerAuth | Implemented | HTTPS и эксплуатация IdP находятся за пределами backend |
| Разграничение доступа | RBAC (user/curator/manager/admin), централизованные policies и university data scope | Implemented | региональный scope менеджера не реализован |
| Регистрация событий | Транзакционный append-only Audit Log для CRUD, workflow, reports, imports и admin | Partial | LOGIN/LOGOUT не эмитятся текущим OIDC flow |
| Контроль целостности | SQL constraints, валидация путей и атомарная запись файлов | Partial | криптографическая неизменяемость аудита не реализована |
| Защита от НСД | secure headers, CORS allowlist, request/file limits, path containment, SQLAlchemy binding | Implemented | инфраструктурный perimeter не входит в репозиторий |
| Передача данных | JWT защищает API от неаутентифицированного доступа | Partial | production HTTPS/TLS должен завершаться на reverse proxy или ingress |
| Хранение | Разделённые roots для attachments и reports, env-based credentials для S3 | Partial | encryption-at-rest не заявляется и не проверяется этим кодом |
| Резервное копирование | Рекомендации для внешней инфраструктуры | Not implemented | encrypted backups и их восстановление не входят в backend |

## Фактический инвентарь данных, потенциально относящихся к ПДн

Инвентарь собран по моделям и схемам этого репозитория:

- `Teacher`: ФИО, email, телефон, квалификации и сертификаты.
- `Responsible`: ФИО, email, телефон, роль и optional Keycloak subject.
- `Student`: external ID, ФИО, группа и даты обучения.
- `User`/OIDC claims: Keycloak subject, username, name, email и роли.
- Audit events: user subject/name, роль, request ID, IP, user-agent и значения изменений.
- Meeting/document/workflow records: actor subjects, авторы, комментарии и метаданные файлов.

Состав не расширяется предположением о «только агрегатах студентов»: таблица
`students` действительно хранит строки студентов.

## Аудит и неизменяемость

Audit API предоставляет application-level append-only доступ: публичного update/delete
маршрута для событий нет. Это **не** криптографическая неизменяемость. CRUD,
workflow, report, import и admin actions пишутся через `AuditService`; надёжного
backend hook для OIDC LOGIN/LOGOUT сейчас нет.

## Ориентировочная таблица ФСТЭК

| Область | Статус | Что фактически есть |
|---|---|---|
| Идентификация и аутентификация | Implemented | Keycloak + JWT/JWKS |
| Разграничение доступа | Implemented | RBAC + data scope |
| Регистрация событий | Partial | audit actions; login/logout gap |
| Контроль целостности | Partial | constraints/path checks; no crypto immutability |
| Защита от НСД | Partial | API baseline; no perimeter controls |
| Антивирус | Not implemented | file AV scanning отсутствует |
| Сетевой периметр | Infrastructure/organizational | firewall/IDS/IPS вне репозитория |
| Backup | Infrastructure/organizational | encrypted backup policy отсутствует |
| Incident response | Not implemented | formal plan и training отсутствуют |

## Не реализовано и известные gaps

- сертифицированные СЗИ и formal certification;
- firewall/IDS/IPS, SIEM и network segmentation;
- encrypted backups, incident response plan, security training;
- asset/threat inventory и formal threat model;
- LOGIN/LOGOUT audit events;
- regional manager scope;
- exact file-type allowlist (сейчас это env contract; пустое значение означает open);
- внешний daily scheduler для фоновых задач;
- TLS termination, если она не предоставлена deployment infrastructure.

## Production recommendations

Перед промышленным запуском провести risk assessment и threat model, выбрать
применимые требования, настроить сегментацию и firewall, централизованный SIEM,
резервное копирование с шифрованием и проверкой восстановления, SAST/DAST,
управление уязвимостями зависимостей и formal compliance/security assessment.

