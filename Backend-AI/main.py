from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_export import router as export_router
from api.routes_legacy import router as legacy_router
from api.routes_planning import router as planning_router
from api.routes_session import router as session_router
from api.state import RuntimeState


def create_app() -> FastAPI:
    app = FastAPI(title="Backend-AI", version="5.0.0")

    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,
        compresslevel=5,
    )

    app.state.runtime = RuntimeState.build()

    app.include_router(session_router)
    app.include_router(planning_router)
    app.include_router(export_router)
    app.include_router(legacy_router)

    # Serve artifacts (sessions/...) for Android to fetch env mesh, overlays, and traces
    # Note: path is relative to process cwd; RuntimeState/session_store uses same convention.
    sessions_dir = Path(app.state.runtime.config.storage.sessions_root)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/sessions", StaticFiles(directory=str(sessions_dir)), name="sessions")

    return app


app = create_app()
