"""One explicit deployment command from the checkout; only Docker is required.

python backend/scripts/start_assistant.py
python backend/scripts/start_assistant.py --model qwen3:4b
The CRM starts before model preparation. A failed pull doesn't disable CRM.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def commands():
    compose = [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        "docker-compose.assistant.yml",
        "--profile",
        "assistant",
    ]
    return [
        compose + ["config", "--quiet"],
        compose + ["up", "-d", "--build", "backend"],
        compose + ["run", "--rm", "--no-deps", "assistant-init"],
        compose + ["exec", "-T", "backend", "python", "-m", "scripts.assistant", "check"],
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("qwen3:1.7b", "qwen3:4b"))
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    if not (root / "docker-compose.yml").is_file():
        raise SystemExit("Run this script from a full project checkout.")
    if not shutil.which("docker"):
        raise SystemExit("Docker Compose is required. Start Docker and run this command again.")
    environment = os.environ.copy()
    if arguments.model:
        environment["ASSISTANT_MODEL"] = arguments.model
    for command in commands():
        print(" ".join(command), flush=True)
        subprocess.run(command, cwd=root, env=environment, check=True)
    print("Assistant is ready. API: /api/v1/assistant. Frontend widget is a separate integration.")


if __name__ == "__main__":
    main()
