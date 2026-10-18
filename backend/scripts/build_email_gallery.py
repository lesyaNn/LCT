"""Build a single offline HTML gallery using the production email renderers.

python -m scripts.build_email_gallery --keycloak-dir /tmp/rtk-emails/keycloak \
    --output ../docs/email-examples.html
"""

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path

from app.config import settings
from app.modules.notifications.email import render_message
from app.modules.notifications.email_templates import logo_data_uri, render_preview_message
from scripts.preview_notification_emails import EXAMPLES, example_notification

CRM_LABELS = (
    ("Назначен ответственный за вуз", "После назначения сотрудника ответственным за вуз."),
    ("Назначена работа", "После назначения ответственного за работу с вузом."),
    ("Доступ к одному вузу", "Администратор предоставил пользователю доступ к одному вузу."),
    ("Доступ к нескольким вузам", "Администратор одновременно предоставил доступ к нескольким вузам."),
    ("Этап Workflow завершён", "Сотрудник завершил этап и перевёл работу на следующий этап."),
    ("Возврат этапа", "Работа возвращена на предыдущий этап с указанием причины."),
    ("Новый комментарий", "Другой сотрудник оставил самостоятельный комментарий в Workflow."),
    ("Приближается срок этапа", "Наступила контрольная дата текущего этапа."),
    ("Задача просрочена", "Истёк срок открытой задачи."),
    ("Заканчивается договор", "Приближается дата окончания действующего договора."),
    ("Заканчивается лицензия", "Приближается дата окончания лицензии."),
    ("Импорт: ошибки в строках", "Импорт обработан, но часть строк содержит ошибки."),
    ("Импорт: не удалось завершить", "Задача импорта завершилась неуспешно."),
    ("Этап просрочен", "Истёк срок текущего этапа Workflow."),
    ("Приближается срок задачи", "Наступила контрольная дата открытой задачи."),
    ("Комментарий с вложением", "Комментарий опубликован с файлом. В письмо попадает текст комментария."),
    ("Workflow завершён", "Сотрудник завершил финальный этап и весь Workflow."),
    ("Добавлена новая задача", "Сотрудник создал задачу на этапе Workflow."),
    ("Задача выполнена", "Сотрудник перевёл задачу из открытого состояния в выполненное."),
)

# Only these account email calls are wired into admin_users.service.
# Both use execute_actions_email(user_id, ["UPDATE_PASSWORD"]).
ACCOUNT_SCENARIOS = (
    ("invite", "Приглашение пользователя",
     "Администратор пригласил нового пользователя. Письмо позволяет установить пароль."),
    ("reset-password", "Обновление пароля администратором",
     "Администратор запросил обновление пароля существующего пользователя. "
     "Используется тот же шаблон, что при приглашении."),
)


class EmailText(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.body = False
        self.parts = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.body = True
        if self.body and tag in {"br", "p", "h1", "h2", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "body":
            self.body = False

    def handle_data(self, data):
        if self.body and data.strip():
            self.parts.append(data.strip() + " ")


def examples(keycloak_dir: Path) -> list[dict]:
    settings.frontend_origin = "https://crm.example.test"
    if len(EXAMPLES) != len(CRM_LABELS):
        raise ValueError("Add a gallery label for every CRM example")
    result = []
    for index, (example, (label, description)) in enumerate(zip(EXAMPLES, CRM_LABELS, strict=True)):
        subject, text = render_message(example_notification(example))
        result.append(dict(id=f"crm-{index + 1}", group="crm", label=label,
                           description=description, kind=example[0], subject=subject,
                           html={"ru": render_preview_message(subject, text)}, text={"ru": text}))
    # Russian matches the realm; inherited templates without app triggers are excluded.
    source = (keycloak_dir / "ru" / "executeActions.html").read_text(encoding="utf-8")
    source = source.replace('src="./img/rostelecom-email.png"', f'src="{logo_data_uri()}"')
    for name, label, description in ACCOUNT_SCENARIOS:
        result.append(dict(id=f"account-{name}", group="account", label=label,
                           description=description, kind="executeActions", subject=label,
                           html={"ru": source},
                           text={"ru": "".join(EmailText(source).parts).strip()}))
    return result


PAGE = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Все письма системы</title>
<style>
:root{font:14px/1.5 Arial,sans-serif;color:#101828;background:#f4f4f7;color-scheme:light;--muted:#667085;--border:#e7e5ed;--surface:#fff;--page:#f4f4f7;--text:#101828;--purple:#7700ff}
*{box-sizing:border-box}body{margin:0}button,input,select{font:inherit}button,select{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #ac79ff;outline-offset:3px}
button{border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:9px;padding:9px 13px;min-height:40px}button:hover{border-color:#b78bf7}button[aria-pressed=true]{background:#7700ff;color:white;border-color:#7700ff}button:disabled{opacity:.4;cursor:default}
header{padding:22px 32px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:22px}.brand{font-size:22px;font-weight:700;letter-spacing:-.6px}.brand span{color:#ff4f12}.brand small{display:block;color:var(--muted);font-size:11px;letter-spacing:.4px;font-weight:400;margin-top:1px}.header-note{margin-left:auto;color:var(--muted);font-size:12px}
.intro{padding:32px 32px 24px;max-width:1480px;margin:auto}.eyebrow{color:var(--purple);font-size:11px;letter-spacing:1.2px;font-weight:700;margin:0 0 8px}h1{font-size:32px;line-height:1.2;letter-spacing:-1px;margin:0 0 10px}.intro p:last-child{color:var(--muted);margin:0;max-width:750px}.count{display:inline-block;font-size:12px;font-weight:400;color:var(--muted);vertical-align:middle;letter-spacing:0;margin-left:10px}
.layout{display:grid;grid-template-columns:285px minmax(0,1fr);gap:24px;max-width:1480px;margin:0 auto;padding:0 32px 36px;align-items:start}.catalog,.workspace{background:var(--surface);border:1px solid var(--border);border-radius:18px;overflow:hidden;min-width:0}.catalog{position:sticky;top:20px}.catalog-head{padding:18px;border-bottom:1px solid var(--border)}input{width:100%;padding:10px 12px;border:1px solid var(--border);border-radius:9px;background:var(--page);color:var(--text)}.catalog-list{max-height:calc(100vh - 170px);overflow:auto;padding:8px}.group-title{color:var(--muted);font-size:10px;font-weight:700;letter-spacing:1px;margin:14px 10px 8px;display:flex;justify-content:space-between}.item{width:100%;border:0;text-align:left;background:transparent;display:flex;align-items:center;gap:10px;padding:10px;min-height:44px;font-size:12px;line-height:1.4;margin:2px 0}.item[aria-current=true]{background:#f0e5ff;color:#6700dc;font-weight:700}.item .number{font-size:10px;color:var(--muted);min-width:16px}.empty{padding:20px;color:var(--muted);font-size:12px}
.workspace-head{padding:22px 24px 18px}.breadcrumb{font-size:11px;color:var(--muted);margin:0 0 8px}.workspace h2{font-size:21px;line-height:1.3;margin:0 0 8px;letter-spacing:-.3px}.description{color:var(--muted);font-size:13px;margin:0;max-width:800px}.availability{font-size:11px;color:var(--muted);padding:10px 12px;margin:14px 0 0;background:var(--page);border-radius:8px;border-left:2px solid #7700ff}.toolbar{padding:14px 24px;border-top:1px solid var(--border);border-bottom:1px solid var(--border);display:flex;flex-wrap:wrap;align-items:center;gap:12px}.control{display:flex;align-items:center;gap:5px}.control-label{color:var(--muted);font-size:11px;margin-right:4px}select{background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:8px;min-height:40px;padding:8px}.download{margin-left:auto;color:var(--purple);font-weight:700}.preview-area{padding:24px 16px;background:#eae9ef;overflow:auto;min-height:300px}.preview-area.dark{background:#16131e}.preview-frame{display:block;width:100%;max-width:760px;border:0;margin:auto;background:#f4f4f7;transition:max-width .15s}.preview-frame.mobile{max-width:375px}.preview-frame.small{max-width:320px}.footer{border-top:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;gap:8px}.position{color:var(--muted);font-size:12px;flex:1;text-align:center}.text-version{padding:0 24px 20px}summary{cursor:pointer;color:var(--muted);font-size:12px}pre{white-space:pre-wrap;word-break:break-word;background:var(--page);padding:18px;border-radius:10px;font:13px/1.7 Arial,sans-serif;color:var(--text);margin:12px 0 0}.mobile-picker{display:none}.bottom-note{max-width:1480px;margin:0 auto 28px;padding:0 32px;color:var(--muted);font-size:11px}.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);max-width:calc(100% - 32px);padding:12px 18px;background:#101828;color:white;border-radius:10px;font-size:12px;overflow-wrap:anywhere;box-shadow:0 4px 20px #0002;z-index:5}.toast[hidden]{display:none}
@media(max-width:900px){.layout{grid-template-columns:minmax(0,1fr);padding:0 16px 24px;gap:16px}.catalog{display:none}.mobile-picker{display:block;width:100%;margin-top:18px}.intro{padding:24px 20px 20px}.workspace-head{padding:20px}.toolbar{padding:12px 16px}.header-note{display:none}header{padding:18px 20px}.bottom-note{padding:0 20px}.download{margin-left:0}.control-label{display:none}h1{font-size:28px}.preview-area{padding:12px 0}.count{font-size:11px;margin-left:4px}.footer{padding:12px}.preview-frame{min-width:0}}
@media(prefers-reduced-motion:reduce){.preview-frame{transition:none}}
</style>
</head>
<body>
<header><div class="brand"><img src="{{LOGO}}" alt="Ростелеком — ИТ Школа" width="174" height="46" style="display:block;height:auto"></div><div class="header-note">Единый каталог email-уведомлений</div></header>
<section class="intro"><p class="eyebrow">КОММУНИКАЦИИ ПРОДУКТА</p><h1>Письма системы <span class="count" id="total"></span></h1><p>Только реализованные сценарии отправки из текущего кода проекта. Выберите письмо, посмотрите его на мобильном экране или в тёмной теме.</p><label class="mobile-picker">Выберите письмо<select id="mobile-select" style="width:100%;margin-top:6px" aria-label="Выберите письмо"></select></label></section>
<div class="layout">
<aside class="catalog" aria-label="Каталог писем"><div class="catalog-head"><input id="search" type="search" placeholder="Найти письмо…" aria-label="Найти письмо"></div><nav class="catalog-list" id="catalog"></nav></aside>
<main class="workspace"><div class="workspace-head"><p class="breadcrumb" id="breadcrumb"></p><h2 id="label"></h2><p class="description" id="description"></p></div>
<div class="toolbar"><div class="control" role="group" aria-label="Ширина письма"><span class="control-label">Экран</span><button type="button" data-width="desktop" aria-pressed="true">Десктоп</button><button type="button" data-width="mobile" aria-pressed="false">375 px</button><button type="button" data-width="small" aria-pressed="false">320 px</button></div><div class="control" role="group" aria-label="Тема письма"><button type="button" data-theme="light" aria-pressed="true">Светлая</button><button type="button" data-theme="dark" aria-pressed="false">Тёмная</button></div><button class="download" id="download" type="button">Скачать HTML ↓</button></div>
<div class="preview-area" id="preview-area"><iframe class="preview-frame" id="preview" title="Предпросмотр письма" sandbox="allow-same-origin" style="height:700px"></iframe></div>
<div class="footer"><button id="previous" type="button" aria-label="Предыдущее письмо">← Назад</button><span class="position" id="position" aria-live="polite"></span><button id="next" type="button" aria-label="Следующее письмо">Далее →</button></div><details class="text-version"><summary>Текстовое представление</summary><pre id="text"></pre></details>
</main></div>
<p class="bottom-note">Демонстрационные данные и ссылки. Письма CRM сформированы текущими шаблонами; письма учётной записи — штатными шаблонами Keycloak с фирменной оболочкой. Файл работает без подключения к сети.</p>
<div class="toast" id="toast" role="status" hidden></div><noscript>Для переключения примеров включите JavaScript. В самих email-письмах JavaScript не используется.</noscript>
<script id="examples" type="application/json">{{DATA}}</script>
<script>
'use strict';
const examples=JSON.parse(document.getElementById('examples').textContent);
const $=id=>document.getElementById(id);
let selected=examples[0], theme='light', width='desktop', toastTimer;
const groups={crm:'Уведомления CRM',account:'Учётная запись · Keycloak'};
const exampleWords={one:'пример',few:'примера',many:'примеров',other:'примера'};
$('total').textContent=`${examples.length} ${exampleWords[new Intl.PluralRules('ru').select(examples.length)]}`;
function makeItem(example,index){const button=document.createElement('button');button.type='button';button.className='item';button.dataset.id=example.id;button.setAttribute('aria-current',String(selected.id===example.id));const number=document.createElement('span');number.className='number';number.textContent=String(index+1).padStart(2,'0');const title=document.createElement('span');title.textContent=example.label;button.append(number,title);button.addEventListener('click',()=>select(example));return button;}
function catalog(){const query=$('search').value.trim().toLocaleLowerCase('ru');$('catalog').replaceChildren();let count=0;for(const [group,name]of Object.entries(groups)){const items=examples.filter(e=>e.group===group&&`${e.label} ${e.description} ${e.subject} ${e.kind}`.toLocaleLowerCase('ru').includes(query));if(!items.length)continue;const title=document.createElement('p');title.className='group-title';title.textContent=`${name} · ${items.length}`;$('catalog').append(title);for(const example of items){$('catalog').append(makeItem(example,examples.indexOf(example)));count++;}}if(!count){const empty=document.createElement('p');empty.className='empty';empty.textContent='Писем по этому запросу нет';$('catalog').append(empty);}}
for(const[group,name]of Object.entries(groups)){const optgroup=document.createElement('optgroup');optgroup.label=name;for(const e of examples.filter(e=>e.group===group)){const option=document.createElement('option');option.value=e.id;option.textContent=e.label;optgroup.append(option);}$('mobile-select').append(optgroup);}
function resize(){const doc=$('preview').contentDocument;if(doc&&doc.body){$('preview').style.height='1px';$('preview').style.height=`${Math.max(280,doc.documentElement.scrollHeight,doc.body.scrollHeight)}px`;}}
function render(){const lang='ru';$('breadcrumb').textContent=`${groups[selected.group]} / ${String(examples.indexOf(selected)+1).padStart(2,'0')}`;$('label').textContent=selected.label;$('description').textContent=selected.description;$('text').textContent=selected.text[lang];$('position').textContent=`${examples.indexOf(selected)+1} из ${examples.length}`;$('previous').disabled=examples.indexOf(selected)===0;$('next').disabled=examples.indexOf(selected)===examples.length-1;$('mobile-select').value=selected.id;document.querySelectorAll('.item').forEach(item=>item.setAttribute('aria-current',String(item.dataset.id===selected.id)));$('preview').className=`preview-frame ${width==='desktop'?'':width}`;$('preview-area').classList.toggle('dark',theme==='dark');$('preview').srcdoc=selected.html[lang].replaceAll('@media (prefers-color-scheme: dark)',theme==='dark'?'@media screen':'@media not all');}
function select(example){selected=example;render();}
$('preview').addEventListener('load',()=>{resize();const doc=$('preview').contentDocument;if(doc){doc.addEventListener('click',event=>{const link=event.target.closest('a');if(link){event.preventDefault();$('toast').textContent=`Демонстрационная ссылка: ${link.getAttribute('href')}`;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}});}});
$('search').addEventListener('input',catalog);$('mobile-select').addEventListener('change',event=>select(examples.find(e=>e.id===event.target.value)));
document.querySelectorAll('[data-theme]').forEach(button=>button.addEventListener('click',()=>{theme=button.dataset.theme;document.querySelectorAll('[data-theme]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();}));document.querySelectorAll('[data-width]').forEach(button=>button.addEventListener('click',()=>{width=button.dataset.width;document.querySelectorAll('[data-width]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));render();}));
$('previous').addEventListener('click',()=>select(examples[examples.indexOf(selected)-1]));$('next').addEventListener('click',()=>select(examples[examples.indexOf(selected)+1]));window.addEventListener('resize',resize);
$('download').addEventListener('click',()=>{const source=selected.html.ru;const url=URL.createObjectURL(new Blob([source],{type:'text/html;charset=utf-8'}));const link=document.createElement('a');link.href=url;link.download=`${selected.id}-ru.html`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
catalog();render();
</script>
</body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keycloak-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = examples(args.keycloak_dir)
    # Keep email markup inside JSON, including literal </script> in dynamic data.
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(PAGE.replace("{{LOGO}}", logo_data_uri()).replace("{{DATA}}", payload),
                           encoding="utf-8")
    print(f"Built {len(data)} examples in one standalone HTML file: {args.output.resolve()}")


if __name__ == "__main__":
    main()
