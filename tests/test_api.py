from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from arena.app import create_app
from arena.problems import PROBLEMS
from arena.store import Capacity, Store

USER_KEY = "test-user-key-" + "u" * 32
WORKER_KEY = "test-worker-key-" + "w" * 32
USER = {"Authorization": "Bearer " + USER_KEY}
WORKER = {"Authorization": "Bearer " + WORKER_KEY}
PAYLOAD = {"problem_id": "pair-sum", "language": "python", "source": "print(sum(map(int,input().split())))"}


@pytest.fixture
def context(tmp_path):
    now = [1000.0]
    app = create_app(tmp_path / "arena.db", USER_KEY, WORKER_KEY, clock=lambda: now[0])
    with TestClient(app) as client:
        yield client, app.state.store, now


def submit(client, idem="request-00001", **changes):
    return client.post(
        "/api/submissions", json={**PAYLOAD, **changes}, headers={**USER, "Idempotency-Key": idem}
    )


def claim(client, worker="test-worker"):
    return client.post("/internal/claim", json={"worker_id": worker}, headers=WORKER)


def complete(client, job, worker="test-worker", **changes):
    results = [
        {
            "index": i,
            "verdict": "accepted",
            "elapsed_ms": 20,
            "stdout": "private-input",
            "stderr": "private-error",
        }
        for i in range(4)
    ]
    return client.post(
        "/internal/jobs/" + job["id"] + "/complete",
        json={"worker_id": worker, "token": job["token"], "kind": "judged", "cases": results, **changes},
        headers=WORKER,
    )


def test_health_and_static(context):
    client, _, _ = context
    assert client.get("/health").json()["mode"] == "local-lab"
    response = client.get("/")
    assert "KodArena" in response.text
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("headers", [{}, WORKER, {"Authorization": "Bearer wrong-key"}])
def test_scoped_user_access(context, headers):
    assert context[0].get("/api/problems", headers=headers).status_code == 401


def test_worker_scope(context):
    assert context[0].post("/internal/claim", headers=USER, json={"worker_id": "worker"}).status_code == 401


def test_public_catalog_hides_private_cases(context):
    problems = context[0].get("/api/problems", headers=USER).json()
    assert len(problems) == 3
    assert "cases" not in problems[0]
    assert len(problems[0]["samples"]) == 1
    assert "-9 3" not in str(problems)


def test_idempotency_replay_and_conflict(context):
    client, _, _ = context
    first, replay = submit(client), submit(client)
    assert first.status_code == 201 and replay.status_code == 200
    assert first.json()["id"] == replay.json()["id"]
    assert submit(client, source="print(0)").status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"problem_id": "unknown"},
        {"language": "bash"},
        {"source": ""},
        {"source": "  "},
        {"source": "ş" * 9000},
        {"source": "\x00"},
        {"extra": "bad"},
    ],
)
def test_submission_validation(context, changes):
    assert submit(context[0], **changes).status_code == 422


def test_request_body_limit(context):
    assert context[0].post("/api/submissions", content=b"x" * 96001, headers=USER).status_code == 413


def test_missing_idempotency_key(context):
    assert context[0].post("/api/submissions", json=PAYLOAD, headers=USER).status_code == 422


def test_hidden_output_discarded_and_lease_not_public(context):
    client, store, _ = context
    job_id = submit(client).json()["id"]
    job = claim(client).json()["job"]
    assert complete(client, job).json()["status"] == "accepted"
    detail = client.get("/api/submissions/" + job_id, headers=USER).json()
    assert "token" not in detail and "spec" not in detail
    assert detail["cases"][0]["stdout"] == "private-input"
    assert detail["cases"][1]["stdout"] == detail["cases"][1]["stderr"] == ""
    with store.connect() as db:
        result = db.execute("SELECT result FROM jobs").fetchone()[0]
    assert result.count("private-input") == 1
    assert complete(client, job).status_code == 409


def test_expired_lease_rejects_old_worker(context):
    client, store, now = context
    submit(client)
    first = claim(client).json()["job"]
    now[0] += 31
    second = claim(client, "replacement").json()["job"]
    assert first["id"] == second["id"] and first["token"] != second["token"]
    assert complete(client, first).status_code == 409
    assert complete(client, second, "replacement").status_code == 200
    assert store.detail(first["id"])["attempts"] == 2


def test_heartbeat_extends_lease(context):
    client, _, now = context
    submit(client)
    job = claim(client).json()["job"]
    now[0] += 20
    assert (
        client.post(
            "/internal/jobs/" + job["id"] + "/heartbeat",
            json={"worker_id": "test-worker", "token": job["token"]},
            headers=WORKER,
        ).status_code
        == 200
    )
    now[0] += 20
    assert claim(client, "other").json()["job"] is None
    assert complete(client, job).status_code == 200


def test_expired_heartbeat_cannot_resurrect(context):
    client, _, now = context
    submit(client)
    job = claim(client).json()["job"]
    now[0] += 30
    response = client.post(
        "/internal/jobs/" + job["id"] + "/heartbeat",
        json={"worker_id": "test-worker", "token": job["token"]},
        headers=WORKER,
    )
    assert response.status_code == 409


def test_worker_single_active_job(context):
    client, _, _ = context
    submit(client)
    submit(client, "request-00002")
    claim(client)
    assert claim(client).status_code == 409
    assert claim(client, "other").json()["job"] is not None


@pytest.mark.parametrize("running", [False, True])
def test_cancel_is_terminal_and_idempotent(context, running):
    client, _, _ = context
    job_id = submit(client).json()["id"]
    job = claim(client).json()["job"] if running else None
    path = "/api/submissions/" + job_id + "/cancel"
    assert client.post(path, headers=USER).status_code == 200
    assert client.post(path, headers=USER).status_code == 200
    if job:
        assert complete(client, job).status_code == 409
    assert claim(client, "other").json()["job"] is None


def test_completed_cannot_cancel(context):
    client, _, _ = context
    submit(client)
    job = claim(client).json()["job"]
    complete(client, job)
    assert client.post("/api/submissions/" + job["id"] + "/cancel", headers=USER).status_code == 409


def test_retry_backoff_and_dead_letter(context):
    client, store, now = context
    job_id = submit(client).json()["id"]
    for attempt in range(3):
        job = claim(client).json()["job"]
        result = complete(client, job, kind="infrastructure_error", cases=[], error="daemon offline")
        assert result.json()["status"] == ("system_error" if attempt == 2 else "queued")
        assert claim(client).json()["job"] is None
        now[0] += 31
    assert store.detail(job_id)["status"] == "system_error"
    assert store.detail(job_id)["attempts"] == 3


def test_repeated_worker_crashes_reach_dead_letter(context):
    client, store, now = context
    job_id = submit(client).json()["id"]
    for i in range(3):
        assert claim(client, "worker-" + str(i)).json()["job"]
        now[0] += 31
    assert claim(client, "last").json()["job"] is None
    assert store.detail(job_id)["status"] == "system_error"


def test_incomplete_results_rejected(context):
    client, _, _ = context
    submit(client)
    job = claim(client).json()["job"]
    assert complete(client, job, cases=[]).status_code == 409
    assert complete(client, job).status_code == 200


def test_fake_worker_token_rejected(context):
    client, _, _ = context
    submit(client)
    job = claim(client).json()["job"]
    assert complete(client, {**job, "token": "x" * 32}).status_code == 409


def test_concurrent_idempotency_and_claim(tmp_path):
    store = Store(tmp_path / "concurrent.db")
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.submit(PAYLOAD, "same-key"), range(16)))
    assert len({r[0] for r in results}) == 1 and sum(r[1] for r in results) == 1
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda i: store.claim("worker-" + str(i)), range(16)))
    assert sum(job is not None for job in claims) == 1


def test_capacity_is_atomic_and_replay_survives_full_queue(tmp_path):
    store = Store(tmp_path / "capacity.db", capacity=1)
    first = store.submit(PAYLOAD, "key-1")
    assert store.submit(PAYLOAD, "key-1")[0] == first[0]
    with pytest.raises(Capacity):
        store.submit(PAYLOAD, "key-2")
    store.cancel(first[0])
    assert store.submit(PAYLOAD, "key-2")[1]


def test_stable_pagination_and_event_replay(context):
    client, store, _ = context
    for i in range(5):
        submit(client, "request-" + str(i))
    first = store.listing(limit=2)
    store.submit(PAYLOAD, "new-after-page")
    second = store.listing(first["next_cursor"], limit=2)
    assert not {r["id"] for r in first["items"]} & {r["id"] for r in second["items"]}
    events = client.get("/api/events?after=0", headers=USER).json()
    assert len(events["items"]) == 6
    assert client.get("/api/events?after=" + str(events["next_cursor"]), headers=USER).json()["items"] == []


def test_problem_snapshot_immutable(context):
    client, _, _ = context
    submit(client)
    original = PROBLEMS["pair-sum"]["version"]
    try:
        PROBLEMS["pair-sum"]["version"] = 999
        assert claim(client).json()["job"]["spec"]["version"] == original
    finally:
        PROBLEMS["pair-sum"]["version"] = original


def test_persists_across_store_restart(tmp_path):
    path = tmp_path / "persist.db"
    store = Store(path)
    job_id, _ = store.submit(PAYLOAD, "persistent")
    reopened = Store(path)
    assert reopened.detail(job_id)["status"] == "queued"
    assert reopened.claim("worker")["id"] == job_id


def test_missing_job(context):
    assert context[0].get("/api/submissions/missing", headers=USER).status_code == 404


def test_keys_required_and_distinct(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(tmp_path / "keys.db", USER_KEY, USER_KEY)


def test_wrong_answer_aggregated(context):
    client, _, _ = context
    submit(client)
    job = claim(client).json()["job"]
    results = [
        {"index": i, "verdict": "wrong_answer" if i == 2 else "accepted", "elapsed_ms": 10} for i in range(4)
    ]
    assert complete(client, job, cases=results).json()["status"] == "wrong_answer"
