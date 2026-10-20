"""Presentation of the existing plain-text notification; no delivery decisions."""

from base64 import b64encode
from functools import lru_cache
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlsplit

from app.config import settings

LOGO_PATH = "/brand/rostelecom-email.png"


@lru_cache(maxsize=1)
def logo_bytes() -> bytes:
    return (Path(__file__).resolve().parents[2] / "assets" / "rostelecom-email.png").read_bytes()


@lru_cache(maxsize=1)
def logo_data_uri() -> str:
    return "data:image/png;base64," + b64encode(logo_bytes()).decode("ascii")


def render_preview_message(subject: str, body: str) -> str:
    """Keep browser previews self-contained; outgoing mail uses a public image URL."""
    return _render_html_message(subject, body, logo_data_uri())


@lru_cache(maxsize=3)
def _template(name: str) -> Template:
    return Template((Path(__file__).with_name("templates") / name).read_text(encoding="utf-8"))


def _frontend_origin() -> str | None:
    origin = settings.frontend_origin.rstrip("/")
    try:
        parsed = urlsplit(origin)
        if (parsed.scheme in {"http", "https"} and parsed.netloc
                and not parsed.username and not parsed.password
                and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                and not any(char.isspace() or ord(char) < 32 for char in origin)):
            return origin
    except ValueError:
        pass
    return None


def logo_url() -> str | None:
    origin = _frontend_origin()
    return origin + LOGO_PATH if origin else None


def _action_url(body: str) -> tuple[str, str | None]:
    """Promote only the existing, final CRM footer to a button and fallback link.

    Everything else remains literal text, including user-supplied HTML and URLs.
    Keep send_email's three-string boundary and the worker's text contract intact.
    """
    content, marker, url = body.rpartition("\n\nОткрыть в CRM: ")
    origin = _frontend_origin()
    if (marker and origin and url.startswith(origin + "/")
            and not any(char.isspace() or ord(char) < 32 for char in url)):
        return content, url
    return body, None


def render_html_message(subject: str, body: str) -> str:
    """Render every event from the exact text already produced by render_message."""
    return _render_html_message(subject, body, logo_url())


def _render_html_message(subject: str, body: str, logo_src: str | None) -> str:
    content, url = _action_url(body)
    # The plain version starts with its subject. Show that once as the HTML h1.
    if content.startswith(subject + "\n\n"):
        content = content[len(subject) + 2:]
    content_html = escape(content).replace("\r\n", "\n").replace("\r", "\n")
    content_html = content_html.replace("\n", "<br>")
    action_html = _template("action.html").substitute(url=escape(url, quote=True)) if url else ""
    brand_html = (_template("brand.html").substitute(logo_src=escape(logo_src, quote=True))
                  if logo_src else
                  '<p class="email-heading" style="margin:0;color:#101828;font-size:22px;'
                  'line-height:30px;font-weight:700;">Ростелеком — ИТ Школа</p>')
    return _template("notification.html").substitute(
        subject=escape(subject), content=content_html, action=action_html,
        brand=brand_html,
    )
