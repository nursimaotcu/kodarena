import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from arena.problems import PROBLEMS

TERMINAL = {
    "accepted",
    "wrong_answer",
    "time_limit",
    "memory_limit",
    "output_limit",
    "runtime_error",
    "system_error",
    "cancelled",
}


class Conflict(Exception):
    pass


class Capacity(Exception):
    pass


class Store:
    """SQLite transaction queue, for workers sharing one API on one host."""

    def __init__(self, path, clock=time.time, lease_seconds=30, max_attempts=3, capacity=100):
        self.path, self.clock = str(path), clock
        self.lease_seconds, self.max_attempts, self.capacity = lease_seconds, max_attempts, capacity
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError("Unsupported database schema")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL, digest TEXT NOT NULL,
                    problem TEXT NOT NULL, language TEXT NOT NULL, source TEXT NOT NULL,
                    spec TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, available REAL NOT NULL,
                    worker TEXT, token TEXT, lease_until REAL, result TEXT, error TEXT
                );
                CREATE INDEX IF NOT EXISTS queue_idx ON jobs(status, available, created);
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    at REAL NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_job ON events(job_id,seq);
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY, seen REAL NOT NULL
                );
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self, write=False):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def event(self, db, job_id, status, detail):
        db.execute(
            "INSERT INTO events(job_id,at,status,detail) VALUES (?,?,?,?)",
            (job_id, self.clock(), status, detail),
        )

    def submit(self, data, idem):
        encoded = json.dumps(data, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        now, job_id = self.clock(), uuid.uuid4().hex
        with self.connect(write=True) as db:
            old = db.execute("SELECT id,digest FROM jobs WHERE idem=?", (idem,)).fetchone()
            if old:
                if old["digest"] != digest:
                    raise Conflict("Bu idempotency anahtarı farklı bir gönderim için kullanılmış.")
                return old["id"], False
            active = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[
                0
            ]
            if active >= self.capacity:
                raise Capacity("Kuyruk dolu; mevcut işlerin tamamlanmasını bekleyin.")
            spec = {
                **PROBLEMS[data["problem_id"]],
                "limits": {"wall_seconds": 2, "memory_mb": 128, "output_bytes": 16384, "pids": 32},
            }
            db.execute(
                """INSERT INTO jobs(id,idem,digest,problem,language,source,spec,status,created,updated,available)
                VALUES (?,?,?,?,?,?,?,'queued',?,?,?)""",
                (
                    job_id,
                    idem,
                    digest,
                    data["problem_id"],
                    data["language"],
                    data["source"],
                    json.dumps(spec),
                    now,
                    now,
                    now,
                ),
            )
            self.event(db, job_id, "queued", "Gönderim kuyruğa alındı.")
        return job_id, True

    def recover(self, db):
        now = self.clock()
        expired = db.execute(
            "SELECT * FROM jobs WHERE status='running' AND lease_until<=?", (now,)
        ).fetchall()
        for row in expired:
            status = "system_error" if row["attempts"] >= self.max_attempts else "queued"
            db.execute(
                "UPDATE jobs SET status=?,updated=?,available=?,worker=NULL,token=NULL,lease_until=NULL,error=? WHERE id=?",
                (status, now, now, "Worker lease expired", row["id"]),
            )
            self.event(
                db,
                row["id"],
                status,
                "Worker bağlantısı kesildi; "
                + ("deneme sınırı doldu." if status == "system_error" else "iş yeniden sırada."),
            )

    def touch_worker(self, db, worker):
        db.execute(
            "INSERT INTO workers(id,seen) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET seen=excluded.seen",
            (worker, self.clock()),
        )

    def claim(self, worker):
        now = self.clock()
        with self.connect(write=True) as db:
            self.touch_worker(db, worker)
            self.recover(db)
            # A worker identifier may own only one live lease.
            if db.execute("SELECT 1 FROM jobs WHERE status='running' AND worker=?", (worker,)).fetchone():
                raise Conflict("Worker zaten bir iş çalıştırıyor.")
            row = db.execute(
                "SELECT * FROM jobs WHERE status='queued' AND available<=? ORDER BY created,id LIMIT 1",
                (now,),
            ).fetchone()
            if row is None:
                return None
            token = secrets.token_urlsafe(32)
            db.execute(
                "UPDATE jobs SET status='running',worker=?,token=?,lease_until=?,attempts=attempts+1,updated=? WHERE id=?",
                (worker, token, now + self.lease_seconds, now, row["id"]),
            )
            self.event(db, row["id"], "running", f"Çalıştırma denemesi {row['attempts'] + 1} başladı.")
            return {
                "id": row["id"],
                "token": token,
                "language": row["language"],
                "source": row["source"],
                "spec": json.loads(row["spec"]),
                "lease_seconds": self.lease_seconds,
            }

    def owned(self, db, job_id, worker, token):
        row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        if (
            row["status"] != "running"
            or row["worker"] != worker
            or not secrets.compare_digest(row["token"] or "", token)
            or row["lease_until"] <= self.clock()
        ):
            raise Conflict("İş sahipliği sona erdi; bu sonuç kabul edilmedi.")
        return row

    def heartbeat(self, job_id, worker, token):
        with self.connect(write=True) as db:
            self.owned(db, job_id, worker, token)
            self.touch_worker(db, worker)
            db.execute(
                "UPDATE jobs SET lease_until=? WHERE id=?", (self.clock() + self.lease_seconds, job_id)
            )

    def finish(self, job_id, worker, token, kind, cases, error):
        with self.connect(write=True) as db:
            row = self.owned(db, job_id, worker, token)
            now = self.clock()
            if kind == "infrastructure_error":
                if cases:
                    raise Conflict("Altyapı hatası test sonuçları içeremez.")
                status = "system_error" if row["attempts"] >= self.max_attempts else "queued"
                delay = min(30, 2 ** row["attempts"])
                db.execute(
                    "UPDATE jobs SET status=?,updated=?,available=?,worker=NULL,token=NULL,lease_until=NULL,error=? WHERE id=?",
                    (status, now, now + delay, error, job_id),
                )
                self.event(
                    db,
                    job_id,
                    status,
                    "Çalıştırma altyapısı hatası; "
                    + (
                        "deneme sınırı doldu."
                        if status == "system_error"
                        else f"{delay} saniye sonra yeniden denenecek."
                    ),
                )
                return status
            spec = json.loads(row["spec"])
            if len(cases) != len(spec["cases"]) or [c["index"] for c in cases] != list(range(len(cases))):
                raise Conflict("Test sonuçları eksik veya sırası hatalı.")
            status = next((c["verdict"] for c in cases if c["verdict"] != "accepted"), "accepted")
            # Private output can reveal hidden inputs, so discard before persistence.
            clean = [
                {
                    **c,
                    "stdout": c["stdout"] if spec["cases"][i]["public"] else "",
                    "stderr": c["stderr"] if spec["cases"][i]["public"] else "",
                    "public": spec["cases"][i]["public"],
                }
                for i, c in enumerate(cases)
            ]
            db.execute(
                "UPDATE jobs SET status=?,updated=?,result=?,error=NULL,token=NULL,lease_until=NULL WHERE id=?",
                (status, now, json.dumps(clean), job_id),
            )
            self.event(db, job_id, status, "Testler tamamlandı.")
            return status

    def cancel(self, job_id):
        with self.connect(write=True) as db:
            row = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            if row["status"] == "cancelled":
                return
            if row["status"] in TERMINAL:
                raise Conflict("Tamamlanan iş iptal edilemez.")
            db.execute(
                "UPDATE jobs SET status='cancelled',updated=?,token=NULL,lease_until=NULL WHERE id=?",
                (self.clock(), job_id),
            )
            self.event(
                db, job_id, "cancelled", "İptal edildi; worker bir sonraki heartbeat kontrolünde duracak."
            )

    def detail(self, job_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise KeyError(job_id)
            spec = json.loads(row["spec"])
            return {
                "id": row["id"],
                "problem_id": row["problem"],
                "title": spec["title"],
                "version": spec["version"],
                "language": row["language"],
                "source": row["source"],
                "status": row["status"],
                "created": row["created"],
                "updated": row["updated"],
                "attempts": row["attempts"],
                "limits": spec["limits"],
                "test_count": len(spec["cases"]),
                "cases": json.loads(row["result"]) if row["result"] else [],
                "events": [
                    dict(e)
                    for e in db.execute(
                        "SELECT seq,at,status,detail FROM events WHERE job_id=? ORDER BY seq", (job_id,)
                    )
                ],
            }

    def listing(self, before=None, limit=30):
        with self.connect() as db:
            # Monotonic event sequence gives a stable insertion-order page boundary.
            rows = db.execute(
                """SELECT j.id,j.problem AS problem_id,j.language,j.status,j.created,j.attempts,e.seq
                FROM jobs j JOIN events e ON e.job_id=j.id AND e.seq=(SELECT MIN(seq) FROM events WHERE job_id=j.id)
                WHERE e.seq < ? ORDER BY e.seq DESC LIMIT ?""",
                (before or 9223372036854775807, limit + 1),
            ).fetchall()
            return {
                "items": [dict(r) for r in rows[:limit]],
                "next_cursor": rows[limit - 1]["seq"] if len(rows) > limit else None,
            }

    def events(self, after):
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 100", (after,))
            ]

    def stats(self):
        with self.connect() as db:
            counts = {r[0]: r[1] for r in db.execute("SELECT status,COUNT(*) FROM jobs GROUP BY status")}
            workers = [
                dict(r)
                for r in db.execute(
                    "SELECT id,seen FROM workers WHERE seen>? ORDER BY id",
                    (self.clock() - self.lease_seconds * 2,),
                )
            ]
            return {
                "counts": counts,
                "total": sum(counts.values()),
                "workers": workers,
                "capacity": self.capacity,
            }
