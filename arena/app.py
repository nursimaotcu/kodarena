import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from arena.models import Claim, Completion, Lease, Submission
from arena.problems import PROBLEMS, public_problems
from arena.store import Capacity, Conflict, Store


class BodyLimit:
    """Enforce size before JSON parsing, including chunked requests."""

    def __init__(self, app, limit=96_000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse({"detail": "İstek gövdesi çok büyük."}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(path=None, api_key=None, worker_key=None, clock=None):
    api_key = api_key or os.environ.get("ARENA_API_KEY", "")
    worker_key = worker_key or os.environ.get("ARENA_WORKER_KEY", "")
    if min(len(api_key), len(worker_key)) < 24 or api_key == worker_key:
        raise RuntimeError(
            "İki farklı, en az 24 karakterlik ARENA_API_KEY ve ARENA_WORKER_KEY ayarlayın. scripts/setup.py kullanabilirsiniz."
        )
    store = Store(path or os.environ.get("ARENA_DB", "data/arena.db"), **({"clock": clock} if clock else {}))

    @asynccontextmanager
    async def lifespan(app):
        # Recovery happens in claim's atomic transaction. No scheduler can race it.
        yield

    app = FastAPI(title="KodArena", version="1.0.0", lifespan=lifespan)
    app.state.store = store
    app.add_middleware(BodyLimit)

    def auth(expected):
        def check(authorization: str = Header(default="")):
            if not secrets.compare_digest(authorization.encode(), f"Bearer {expected}".encode()):
                raise HTTPException(401, "Erişim anahtarı geçersiz.")

        return check

    user, worker = Depends(auth(api_key)), Depends(auth(worker_key))

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(Capacity)
    async def capacity_handler(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=429, headers={"Retry-After": "5"})

    @app.exception_handler(KeyError)
    async def missing_handler(request, exc):
        return JSONResponse({"detail": "Gönderim bulunamadı."}, status_code=404)

    @app.get("/health")
    def health():
        with store.connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "mode": "local-lab"}

    @app.get("/api/problems", dependencies=[user])
    def problems():
        return public_problems()

    @app.post("/api/submissions", dependencies=[user])
    def submit(
        data: Submission,
        idempotency_key: str = Header(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$"),
    ):
        if data.problem_id not in PROBLEMS:
            raise HTTPException(422, "Bilinmeyen problem.")
        if len(data.source.encode()) > 16_000 or not data.source.strip() or "\x00" in data.source:
            raise HTTPException(
                422, "Kod boş olamaz; UTF-8 boyutu en fazla 16.000 bayt olabilir ve NUL içeremez."
            )
        job_id, created = store.submit(data.model_dump(), idempotency_key)
        return JSONResponse({"id": job_id, "created": created}, status_code=201 if created else 200)

    @app.get("/api/submissions", dependencies=[user])
    def listing(before: int | None = Query(None, ge=1), limit: int = Query(30, ge=1, le=100)):
        return store.listing(before, limit)

    @app.get("/api/submissions/{job_id}", dependencies=[user])
    def detail(job_id: str):
        return store.detail(job_id)

    @app.post("/api/submissions/{job_id}/cancel", dependencies=[user])
    def cancel(job_id: str):
        store.cancel(job_id)
        return {"status": "cancelled"}

    @app.get("/api/events", dependencies=[user])
    def events(after: int = Query(0, ge=0)):
        items = store.events(after)
        return {"items": items, "next_cursor": items[-1]["seq"] if items else after}

    @app.get("/api/stats", dependencies=[user])
    def stats():
        return store.stats()

    @app.post("/internal/claim", dependencies=[worker])
    def claim(data: Claim):
        return {"job": store.claim(data.worker_id)}

    @app.post("/internal/jobs/{job_id}/heartbeat", dependencies=[worker])
    def heartbeat(job_id: str, data: Lease):
        store.heartbeat(job_id, data.worker_id, data.token)
        return {"status": "owned"}

    @app.post("/internal/jobs/{job_id}/complete", dependencies=[worker])
    async def complete(job_id: str, data: Completion):
        status = await run_in_threadpool(
            store.finish,
            job_id,
            data.worker_id,
            data.token,
            data.kind,
            [c.model_dump() for c in data.cases],
            data.error,
        )
        return {"status": status}

    app.mount(
        "/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "static", html=True), name="ui"
    )
    return app
