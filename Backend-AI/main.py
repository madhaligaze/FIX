from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_export import router as export_router
from api.routes_legacy import router as legacy_router
from api.routes_planning_v2 import router as planning_router
from api.routes_session_v2 import router as session_router
from api.state import RuntimeState
from observability.logging import setup_json_logging
from security.audit import write_audit_event
from security.auth import require_api_key


def init_runtime() -> RuntimeState:
    build = getattr(RuntimeState, "build", None)
    if callable(build):
        return RuntimeState.build()
    raise RuntimeError("RuntimeState.build is unavailable")


def create_app() -> FastAPI:
    setup_json_logging(level="INFO")
    app = FastAPI(title="Backend-AI", version="5.0.0")

    app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
    app.state.runtime = init_runtime()

    @app.middleware("http")
    async def auth_and_audit(request: Request, call_next):
        role = require_api_key(request)
        try:
            write_audit_event(request.app.state.runtime.store.root, {"path": request.url.path, "method": request.method, "role": role})
        except Exception:
            pass
        return await call_next(request)

    app.include_router(session_router)
    app.include_router(planning_router)
    app.include_router(export_router)
    app.include_router(legacy_router)

    sessions_dir = Path(app.state.runtime.config.storage.sessions_root)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/sessions", StaticFiles(directory=str(sessions_dir)), name="sessions")

    @app.get("/health")
    def health() -> dict[str, object]:
        return {"status": "ok", "version": app.version, "modules": {"legacy": True, "pipeline": True}}

    return app


app = create_app()
