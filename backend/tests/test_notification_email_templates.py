"""Content parity, safe markup and destinations for every notification scenario."""

from html.parser import HTMLParser

import pytest

from app.config import settings
from app.modules.notifications.email import render_message, target_path
from app.modules.notifications.email_templates import LOGO_CID, render_html_message
from scripts.preview_notification_emails import EXAMPLES, example_notification


class EmailHTML(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.tags = []
        self.images = []
        self.text = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "a":
            self.links.append(dict(attrs)["href"])
        if tag == "img":
            self.images.append(dict(attrs))
        if tag == "br":
            self.text.append("\n")

    def handle_data(self, data):
        self.text.append(data)


@pytest.mark.parametrize("example", EXAMPLES)
def test_all_scenarios_preserve_text_and_destination(monkeypatch, example):
    monkeypatch.setattr(settings, "frontend_origin", "https://crm.example.test")
    notification = example_notification(example)
    subject, body = render_message(notification)
    url = "https://crm.example.test" + target_path(notification)
    # The original plain text contract stays byte-for-byte intact.
    assert body == f"{notification.title}\n\n{notification.message}\n\nОткрыть в CRM: {url}"
    html = EmailHTML(render_html_message(subject, body))
    assert html.links == [url, url]
    assert notification.message in "".join(html.text)
    assert subject in "".join(html.text)
    assert html.tags.count("h1") == 1
    assert not {"script", "iframe", "link"}.intersection(html.tags)
    assert len(html.images) == 1
    assert html.images[0]["src"] == f"cid:{LOGO_CID}"
    assert html.images[0]["alt"] == "Ростелеком — ИТ Школа"


def test_escaping_multiline_and_long_dynamic_values(monkeypatch):
    monkeypatch.setattr(settings, "frontend_origin", "https://crm.example.test")
    notification = example_notification(EXAMPLES[6])
    notification.title = '<img src="x" onerror="alert(1)"> & $title'
    notification.message = ('А <script>alert("x")</script> & "Б"\n\n'
                            + "ДлинноеНазвание" * 150 + "\nКод: 001234")
    notification.entity_id = 'id/with?query="value"&x=1'
    subject, body = render_message(notification)
    source = render_html_message(subject, body)
    html = EmailHTML(source)
    assert notification.message in "".join(html.text)
    assert notification.title in "".join(html.text)
    assert "script" not in html.tags and len(html.images) == 1
    assert html.images[0]["src"] == f"cid:{LOGO_CID}"
    assert html.links == [settings.frontend_origin + target_path(notification)] * 2
    assert "%2F" in html.links[0] and "%26" in html.links[0]


@pytest.mark.parametrize("origin", [
    "", "javascript:alert(1)", "https://crm.example.test/path", "https://user:pass@crm.example.test",
    "https://crm.example.test?x=1", "https://crm.example.test#fragment",
])
def test_no_action_without_usable_origin(monkeypatch, origin):
    monkeypatch.setattr(settings, "frontend_origin", origin)
    row = example_notification(EXAMPLES[0])
    subject, body = render_message(row)
    html = EmailHTML(render_html_message(subject, body))
    assert html.links == []
    assert row.message in "".join(html.text)
    assert "Если кнопка" not in "".join(html.text)


@pytest.mark.parametrize("suffix", [
    "javascript:alert(1)", "https://evil.example/path", "https://crm.example.test.evil.example/path",
    "https://crm.example.test/path\nextra text", "https://crm.example.test/path\t",
])
def test_user_supplied_footer_is_never_promoted_to_external_action(monkeypatch, suffix):
    monkeypatch.setattr(settings, "frontend_origin", "https://crm.example.test")
    body = "Сообщение\n\nОткрыть в CRM: " + suffix
    html = EmailHTML(render_html_message("Заголовок", body))
    assert not html.links
    assert body in "".join(html.text)


def test_unknown_event_empty_title_and_existing_user_footer(monkeypatch):
    monkeypatch.setattr(settings, "frontend_origin", "https://crm.example.test")
    row = example_notification(EXAMPLES[0])
    row.type, row.entity_type, row.title = "future_event", "future_entity", " "
    row.message = "Первая строка\n\nОткрыть в CRM: https://user-supplied.example/path"
    subject, body = render_message(row)
    html = EmailHTML(render_html_message(subject, body))
    assert subject == "Уведомление CRM"
    assert html.links == ["https://crm.example.test/notifications"] * 2
    assert row.message in "".join(html.text)
