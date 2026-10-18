"""Verify the preview harness preserved base email text, links and action data."""

import sys
from html.parser import HTMLParser
from pathlib import Path


class Email(HTMLParser):
    def __init__(self, path):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.text = []
        self.links = []
        self.headings = []
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
        if self.in_body and tag == "a":
            self.links.append(dict(attrs)["href"])
        if tag == "h1":
            self.headings.append(tag)

    def handle_endtag(self, tag):
        if tag == "body":
            self.in_body = False

    def handle_data(self, data):
        if self.in_body:
            self.text.append(data)

    @property
    def normalized_text(self):
        return " ".join("".join(self.text).split())


def main():
    root = Path(sys.argv[1])
    count = 0
    for base_path in sorted(root.glob("*/base/*.html")):
        updated_path = base_path.parent.parent / base_path.name
        base, updated = Email(base_path), Email(updated_path)
        assert base.normalized_text in updated.normalized_text, updated_path
        if base.links:
            assert updated.links == base.links + [base.links[0]] * 2, updated_path
        else:
            assert updated.links == [], updated_path
        if base_path.name == "workflow-notification.html":
            assert updated.headings == [], updated_path
        else:
            assert updated.headings == ["h1"], updated_path
            generic = ("Уведомление об учётной записи", "Account notification")
            assert not any(title in updated.normalized_text for title in generic), updated_path
        if base_path.name == "email-verification-with-code.html":
            assert "001234" in updated.normalized_text, updated_path
        count += 1
    assert count, f"No base comparisons in {root}"
    print(f"Verified content, destinations and headings for {count} inherited Keycloak templates")


if __name__ == "__main__":
    main()
