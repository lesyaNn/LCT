"""Deployment shape without starting containers or downloading models in CI."""

from pathlib import Path

from scripts.start_assistant import commands


def test_deploy_validates_then_starts_crm_then_initializes_and_checks():
    plan = commands()
    assert len(plan) == 4
    assert plan[0][-2:] == ["config", "--quiet"]
    assert plan[1][-4:] == ["up", "-d", "--build", "backend"]
    assert plan[2][-4:] == ["run", "--rm", "--no-deps", "assistant-init"]
    assert plan[3][-4:] == ["python", "-m", "scripts.assistant", "check"]
    assert all(command[:2] == ["docker", "compose"] for command in plan)


def test_container_setup_has_no_model_downloads_in_http_or_api_startup():
    root = Path(__file__).resolve().parents[2]
    overlay = (root / "docker-compose.assistant.yml").read_text(encoding="utf-8")
    assert 'command: ["python", "-m", "scripts.assistant", "bootstrap"]' in overlay
    assert "service_completed_successfully" not in overlay
    assert "11434:" not in overlay
    assert ":/app/assistant-docs:ro" in overlay
