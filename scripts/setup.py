"""Create local keys without printing them or replacing existing configuration."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
try:
    with path.open("x", encoding="utf-8") as file:
        file.write("ARENA_API_KEY=" + secrets.token_urlsafe(36) + "\n")
        file.write("ARENA_WORKER_KEY=" + secrets.token_urlsafe(36) + "\n")
        file.write("ARENA_DB=data/arena.db\nARENA_URL=http://127.0.0.1:5200\n")
    print("Created .env. Open it locally to copy ARENA_API_KEY into the dashboard.")
except FileExistsError:
    print(".env already exists; left unchanged.")
