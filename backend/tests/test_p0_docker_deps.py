"""P0-5 guard: backend Dockerfile stays a superset of pyproject deps.

Pure-unit: parses files, no Docker needed.
"""
import re
import tomllib
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
PYPROJECT = BACKEND / "pyproject.toml"
DOCKERFILE = BACKEND / "Dockerfile"

# pep-508 name normalization for the comparison below.
_NORM = re.compile(r"[-_.]+")


def _norm(name: str) -> str:
    return _NORM.sub("-", name).lower()


def _wanted() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    names: set[str] = set()
    for dep in data["project"]["dependencies"]:
        base = re.split(r"[<>=!~;\s\[]", dep, maxsplit=1)[0].strip()
        if base:
            names.add(_norm(base))
    return names


def _installed() -> set[str]:
    text = DOCKERFILE.read_text(encoding="utf-8")
    run_lines = [ln for ln in text.splitlines() if "pip install" in ln]
    assert run_lines, "no pip install line in Dockerfile"
    names: set[str] = set()
    for token in re.split(r"\s+", " ".join(run_lines)):
        token = token.strip().strip("\"'")
        if not token or token in {"RUN", "pip", "install", "--no-cache-dir", "&&"}:
            continue
        if token.startswith("-") or token.startswith("$") or "/" in token:
            continue
        base = re.split(r"[<>=!~;\[]", token, maxsplit=1)[0].strip().strip("\"'")
        if base and re.fullmatch(r"[A-Za-z0-9_.\-]+", base):
            names.add(_norm(base))
    return names


def test_dockerfile_covers_pyproject_deps():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    if re.search(r"(?m)^COPY\s+pyproject\.toml\s+\./?\s*$", dockerfile) and re.search(
        r"(?m)^RUN\s+pip install --no-cache-dir \.\s*$", dockerfile
    ):
        return  # The package metadata is the dependency source for the image.
    missing = _wanted() - _installed() - {"uvicorn"}  # uvicorn[standard] extra form
    # uvicorn standard extra installs as dist "uvicorn"; accept either token.
    if "uvicorn" in _wanted():
        assert "uvicorn" in _installed() or "uvicornstandard" in _installed()
        missing.discard("uvicorn")
    assert not missing, f"Dockerfile misses pyproject deps: {sorted(missing)}"


def test_dockerfile_runs_non_root():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert re.search(r"(?m)^USER\s+\S+", text), "Dockerfile must set USER (non-root)"
