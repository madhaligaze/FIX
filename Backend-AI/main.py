from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes_export import router as export_router
from api.routes_legacy import router as legacy_router
from api.routes_planning import router as planning_router
from api.routes_session import router as session_router
from api.state import RuntimeState
from config.loader import load_config
from modules.detector_2d import Detector2D
from policy.policy_config import PolicyConfig
from session.session_store import SessionStore


def init_runtime() -> RuntimeState:
    config = load_config()
    store = SessionStore(config.get("paths", {}).get("artifacts_root", "sessions"))
    policy = PolicyConfig.from_config(config)
    runtime = RuntimeState(config=config, store=store, policy=policy)
    runtime.perception_unavailable = not Detector2D().available
    return runtime


def create_app() -> FastAPI:
    app = FastAPI(title="Backend-AI", version="5.0.0")

    app.add_middleware(
        GZipMiddleware,
        minimum_size=1000,
        compresslevel=5,
    )

    app.state.runtime = init_runtime()

    app.include_router(session_router)
    app.include_router(planning_router)
    app.include_router(export_router)
    app.include_router(legacy_router)

    # Serve artifacts (sessions/...) for Android to fetch env mesh, overlays, and traces
    # Note: path is relative to process cwd; RuntimeState/session_store uses same convention.
    app.mount("/sessions", StaticFiles(directory="sessions"), name="sessions")

    @app.get("/health")
    def health():
        return {"status": "ok", "version": app.version, "modules": {"legacy": True, "pipeline": True}}

    return app


app = create_app()
