#!/usr/bin/env python3
"""
Replace placeholder APP_SECRET_KEY / JWT_SECRET_KEY in .env so the API can boot.

Pydantic rejects values starting with 'change-me' (see app.core.config.Settings).
Run automatically from scripts/setup.sh; safe to re-run — only touches placeholder lines.

Docker Compose injects env_file at *container create* time. `docker compose restart`
does NOT reload .env — after this script updates secrets, we recreate backend + worker
(unless DOCBASE_NO_DOCKER_RECREATE=1).
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"


def _substitute_placeholder_keys(content: str) -> tuple[str, list[str]]:
    changed: list[str] = []
    out = content
    for key in ("APP_SECRET_KEY", "JWT_SECRET_KEY"):
        pattern = rf"^({re.escape(key)})=(change-me[^\n]*)$"
        if not re.search(pattern, out, flags=re.MULTILINE):
            continue
        new_secret = secrets.token_hex(32)
        out = re.sub(
            pattern,
            rf"\1={new_secret}",
            out,
            count=1,
            flags=re.MULTILINE,
        )
        changed.append(key)
    return out, changed


def _try_recreate_backend_worker() -> None:
    """Apply new env_file values — required after editing .env."""
    if os.environ.get("DOCBASE_NO_DOCKER_RECREATE", "").strip() in ("1", "true", "yes"):
        print(
            "Skipped Docker recreate (DOCBASE_NO_DOCKER_RECREATE is set). "
            "Run: docker compose up -d --force-recreate backend worker"
        )
        return
    if not shutil.which("docker") or not COMPOSE_FILE.is_file():
        print(
            "Reload .env into containers with:\n"
            "  docker compose up -d --force-recreate backend worker"
        )
        return
    r = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "up",
            "-d",
            "--force-recreate",
            "backend",
            "worker",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        print("Recreated backend + worker so they load the updated .env.")
    else:
        err = (r.stderr or r.stdout or "").strip()
        print("Docker recreate failed; run manually:", file=sys.stderr)
        print(
            "  docker compose up -d --force-recreate backend worker",
            file=sys.stderr,
        )
        if err:
            print(err, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix placeholder secrets and reload Docker env.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Only recreate backend/worker (use after any manual .env edit Compose should pick up)",
    )
    args = parser.parse_args()

    if args.recreate:
        _try_recreate_backend_worker()
        return 0

    if not ENV_PATH.exists():
        print("ERROR: .env not found. Copy .env.example to .env first.", file=sys.stderr)
        return 1
    text = ENV_PATH.read_text(encoding="utf-8")
    new_text, keys = _substitute_placeholder_keys(text)
    if keys:
        ENV_PATH.write_text(new_text, encoding="utf-8")
        print("Generated local dev secrets for: " + ", ".join(keys))
        _try_recreate_backend_worker()
    else:
        print("No placeholder APP_SECRET_KEY / JWT_SECRET_KEY found; .env unchanged.")
        print(
            "If you edited .env but containers still use old values, run:\n"
            "  python3 scripts/ensure_dev_secrets.py --recreate"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
