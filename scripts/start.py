"""Load local configuration and start exactly one API or worker process."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.chdir(root)
if (root / ".env").exists():
    for line in (root / ".env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, value = line.split("=", 1)
            os.environ.setdefault(name, value)
parser = argparse.ArgumentParser()
parser.add_argument("mode", choices=["api", "worker"])
parser.add_argument("--id", help="Unique worker ID, e.g. worker-2")
args = parser.parse_args()
if args.mode == "api":
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "arena.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        "5200",
        "--no-access-log",
    ]
else:
    if args.id:
        os.environ["ARENA_WORKER_ID"] = args.id
    command = [sys.executable, "-m", "arena.worker"]
try:
    raise SystemExit(subprocess.call(command))
except KeyboardInterrupt:
    pass
