"""Small offline checks for the Keycloak 26.7.4 email theme."""

from pathlib import Path
import re


ROOT = Path(__file__).parent / "themes" / "lct-crm" / "email"
CUSTOM = ("executeActions.ftl", "password-reset.ftl", "email-verification.ftl")


def main() -> None:
    props = (ROOT / "theme.properties").read_text(encoding="utf-8")
    assert "parent=base" in props.splitlines()
    assert "locales=ru,en" in props.splitlines()
    assert (ROOT / "html" / "template.ftl").is_file()
    for name in CUSTOM:
        assert (ROOT / "html" / name).is_file(), name
        assert (ROOT / "text" / name).is_file(), name

    keys = {}
    for lang in ("ru", "en"):
        path = ROOT / "messages" / f"messages_{lang}.properties"
        lines = path.read_text(encoding="utf-8").splitlines()
        keys[lang] = {line.split("=", 1)[0] for line in lines if "=" in line}
        assert len(keys[lang]) == sum("=" in line for line in lines), path
    assert keys["ru"] == keys["en"]

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?:keycloak|localhost|127\.0\.0\.1|192\.168\.)", content, re.I), path
        assert "SMTP_PASSWORD" not in content and "KC_DB_PASSWORD" not in content, path
        for key in re.findall(r'msg\("([^"]+)"', content):
            if key.startswith("lct"):
                assert key in keys["ru"], (path, key)
    print("Keycloak email theme structure and message keys: OK")


if __name__ == "__main__":
    main()
