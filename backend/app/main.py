import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import SessionLocal, init_db
from .routers import admin, analytics, auth, documents, extractions, query, reports

API_PREFIXES = ("/auth", "/documents", "/reports", "/analytics", "/query", "/extractions", "/admin")
_buckets: dict[str, deque] = defaultdict(deque)


def bootstrap_admin():
    from .auth import hash_password
    from .models import User

    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            return
        password = settings.admin_password or secrets.token_urlsafe(12)
        db.add(
            User(
                username=settings.admin_user,
                password_hash=hash_password(password),
                role="admin",
                subsidiary="",
            )
        )
        db.commit()
        if settings.admin_password:
            print(f"[setup] created admin user '{settings.admin_user}' from ADMIN_PASSWORD env")
        else:
            print(f"[setup] created admin user '{settings.admin_user}' with one-time password: {password}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
    except Exception as e:
        print(f"[warn] DB init failed (is the database up?): {e}")
    try:
        bootstrap_admin()
    except Exception as e:
        print(f"[warn] admin bootstrap failed: {e}")
    yield


app = FastAPI(title="CMPDI AI Reporting Platform", version="0.3.0", lifespan=lifespan)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith(API_PREFIXES):
        ip = request.client.host if request.client else "?"
        now = time.time()
        bucket = _buckets[ip]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= settings.rate_limit_per_min:
            return JSONResponse({"detail": "rate limit exceeded"}, status_code=429)
        bucket.append(now)
    return await call_next(request)


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(reports.router)
app.include_router(analytics.router)
app.include_router(query.router)
app.include_router(extractions.router)
app.include_router(admin.router)

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
_DIST_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "..", "frontend_dist"),
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"),
]
class CachedStaticFiles(StaticFiles):
    """Hashed Vite assets - safe to cache forever."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp


_DIST = next((d for d in _DIST_CANDIDATES if os.path.exists(d)), "")
if _DIST:
    app.mount("/assets", CachedStaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")


@app.middleware("http")
async def spa_html_fallback(request: Request, call_next):
    """Browser navigation (Accept: text/html) to API-colliding paths (e.g. /documents) must get
    the React app, not a 401 from the API route. Fetch calls (Accept: */*) pass through to APIs."""
    if (
        request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
        and not request.url.path.startswith("/assets")
    ):
        idx = os.path.join(_DIST, "index.html") if _DIST else os.path.join(_STATIC_DIR, "index.html")
        return FileResponse(idx, headers={"Cache-Control": "no-cache"})
    return await call_next(request)


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if _DIST:
        f = os.path.join(_DIST, full_path)
        if full_path and os.path.isfile(f):
            return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable"})
        return FileResponse(os.path.join(_DIST, "index.html"), headers={"Cache-Control": "no-cache"})
    return FileResponse(os.path.join(_STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})
