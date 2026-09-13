"""Worker has Docker access; API has none. Run multiple workers with unique identifiers."""

import argparse
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid

from arena.sandbox import DockerSandbox, InfrastructureError, LostLease, judge

log = logging.getLogger("kodarena.worker")


class Coordinator:
    def __init__(self, base, key, worker_id):
        self.base, self.key, self.worker_id = base.rstrip("/"), key, worker_id

    def post(self, path, payload):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps({"worker_id": self.worker_id, **payload}, ensure_ascii=False).encode(),
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.load(response)


def process_job(client, job, sandbox):
    abort, done = threading.Event(), threading.Event()

    def renew():
        while not done.wait(min(3, job["lease_seconds"] / 3)):
            try:
                client.post(f"/internal/jobs/{job['id']}/heartbeat", {"token": job["token"]})
            except (urllib.error.URLError, TimeoutError, OSError):
                abort.set()
                return

    heartbeat = threading.Thread(target=renew, daemon=True)
    heartbeat.start()
    try:
        try:
            cases = judge(job, sandbox, abort)
            result = {"kind": "judged", "cases": cases}
        except InfrastructureError:
            log.exception("Sandbox infrastructure failure for job %s", job["id"])
            result = {"kind": "infrastructure_error", "error": "Sandbox unavailable; inspect worker logs"}
        if not abort.is_set():
            client.post(f"/internal/jobs/{job['id']}/complete", {"token": job["token"], **result})
    except LostLease:
        log.info("Job %s stopped after cancellation/lease loss", job["id"])
    finally:
        done.set()
        heartbeat.join(timeout=6)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one available job")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    key = os.environ.get("ARENA_WORKER_KEY", "")
    if len(key) < 24:
        raise SystemExit("ARENA_WORKER_KEY is required; use scripts/start.py worker")
    sandbox = DockerSandbox()
    try:
        sandbox.preflight()
    except InfrastructureError as exc:
        raise SystemExit(
            f"Worker not started: {exc}. Start Docker and pull runtime images. No host execution fallback exists."
        ) from exc
    client = Coordinator(
        os.environ.get("ARENA_URL", "http://127.0.0.1:5200"),
        key,
        os.environ.get("ARENA_WORKER_ID", "worker-" + uuid.uuid4().hex[:8]),
    )
    log.info("Worker %s ready", client.worker_id)
    try:
        while True:
            try:
                job = client.post("/internal/claim", {})["job"]
                if job:
                    process_job(client, job, sandbox)
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise SystemExit("Worker key rejected") from exc
                log.warning(
                    "Coordinator returned HTTP %s; lease recovery will handle unfinished jobs", exc.code
                )
            except (urllib.error.URLError, TimeoutError, OSError):
                log.warning("Coordinator unavailable; retrying")
            if args.once:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Worker stopped")


if __name__ == "__main__":
    main()
