from __future__ import annotations

from fastapi import FastAPI

from api.routes_export import router as export_router
from api.routes_legacy import router as legacy_router
from api.routes_planning import router as planning_router
from api.routes_session import router as session_router
from api.state import RuntimeState
from config.loader import load_config
from modules.detector_2d import Detector2D
from policy.policy_config import PolicyConfig
from session.session_store import SessionStore

app = FastAPI(title="Backend-AI", version="5.0.0")


def init_runtime() -> RuntimeState:
    config = load_config()
    store = SessionStore(config.get("paths", {}).get("artifacts_root", "sessions"))
    policy = PolicyConfig.from_config(config)
    runtime = RuntimeState(config=config, store=store, policy=policy)
    runtime.perception_unavailable = not Detector2D().available
    return runtime


app.state.runtime = init_runtime()

app.include_router(session_router)
app.include_router(planning_router)
app.include_router(export_router)
app.include_router(legacy_router)


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version, "modules": {"legacy": True, "pipeline": True}}
