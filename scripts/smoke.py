"""Exercise the actual API and Docker-backed worker. Both must already be running."""

import json
import os
import time
import urllib.request
import uuid
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if (root / ".env").exists():
    for line in (root / ".env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, value = line.split("=", 1)
            os.environ.setdefault(name, value)
base = os.environ.get("ARENA_URL", "http://127.0.0.1:5200")
key = os.environ["ARENA_API_KEY"]


def call(path, data=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Idempotency-Key": uuid.uuid4().hex,
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


assert call("/health")["status"] == "ok"
scenarios = [
    ("python", "print(sum(map(int,input().split())))", "accepted"),
    (
        "javascript",
        "console.log(require('fs').readFileSync(0,'utf8').trim().split(/\\s+/).map(Number).reduce((a,b)=>a+b,0))",
        "accepted",
    ),
    ("python", "print(0)", "wrong_answer"),
    ("python", "while True: pass", "time_limit"),
]
for language, source, expected in scenarios:
    job = call("/api/submissions", {"problem_id": "pair-sum", "language": language, "source": source})
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = call("/api/submissions/" + job["id"])
        if result["status"] not in ("queued", "running"):
            break
        time.sleep(1)
    assert result["status"] == expected, (expected, result["status"])
    print(language + ": " + expected)
print("Real API + worker smoke passed.")
