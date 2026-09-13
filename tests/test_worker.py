import threading
import urllib.error

from arena.sandbox import Execution, InfrastructureError, LostLease
from arena.worker import process_job


def job():
    return {
        "id": "test-job",
        "token": "test-token",
        "lease_seconds": 0.03,
        "language": "python",
        "source": "unused",
        "spec": {"limits": {}, "cases": [{"input": "4 7", "expected": "11"}]},
    }


def test_worker_submits_judged_result():
    class Client:
        calls = []

        def post(self, path, payload):
            self.calls.append((path, payload))

    class Sandbox:
        def run(self, *args):
            return Execution("ok", "11", "", 10)

    client = Client()
    process_job(client, job(), Sandbox())
    assert client.calls[-1][0].endswith("/complete")
    assert client.calls[-1][1]["cases"][0]["verdict"] == "accepted"


def test_worker_reports_infrastructure_error():
    class Client:
        calls = []

        def post(self, path, payload):
            self.calls.append((path, payload))

    class Sandbox:
        def run(self, *args):
            raise InfrastructureError("test-only failure")

    client = Client()
    process_job(client, job(), Sandbox())
    assert client.calls[-1][1]["kind"] == "infrastructure_error"


def test_worker_stops_when_heartbeat_rejected():
    aborted = threading.Event()

    class Client:
        calls = []

        def post(self, path, payload):
            self.calls.append(path)
            raise urllib.error.HTTPError(path, 409, "lease lost", None, None)

    class Sandbox:
        def run(self, language, source, stdin, limits, abort):
            assert abort.wait(timeout=2)
            aborted.set()
            raise LostLease()

    client = Client()
    process_job(client, job(), Sandbox())
    assert aborted.is_set()
    assert all(path.endswith("/heartbeat") for path in client.calls)
