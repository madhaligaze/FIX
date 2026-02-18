from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["export"])


@router.get("/session/{session_id}/export/latest")
def export_latest(request: Request, session_id: str):
    state = request.app.state.runtime
    rev_id = state.last_rev.get(session_id)
    if not rev_id:
        latest_path = state.store.session_root(session_id) / "exports" / "latest.json"
        if latest_path.exists():
            rev_id = json.loads(latest_path.read_text(encoding="utf-8"))["rev_id"]
        else:
            raise HTTPException(status_code=404, detail="No export available")
    return state.store.load_export(session_id, rev_id)
