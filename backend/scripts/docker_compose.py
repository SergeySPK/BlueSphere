import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "backend" / ".env.demo"


def main() -> int:
    values = dotenv_values(ENV_FILE)
    database_url = values.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL отсутствует в backend/.env.demo")

    url = make_url(database_url)

    if url.host != "localhost":
        raise RuntimeError("Ожидался localhost в DATABASE_URL из backend/.env.demo")

    docker_url = url.set(host="host.docker.internal")

    env = os.environ.copy()
    env["DATABASE_URL_DOCKER"] = docker_url.render_as_string(hide_password=False)

    command = ["docker", "compose", *sys.argv[1:]]

    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
