from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request


@dataclass(frozen=True)
class ApiKey:
    key: str
    role: str


def _load_keys(config: dict[str, Any]) -> list[ApiKey]:
    sec = (config or {}).get("security") or {}
    keys = sec.get("api_keys") or []
    out: list[ApiKey] = []
    for item in keys:
        if not isinstance(item, dict):
            continue
        k = str(item.get("key") or "")
        r = str(item.get("role") or "operator")
        if k:
            out.append(ApiKey(key=k, role=r))
    return out


def require_api_key(request: Request) -> str:
    state = request.app.state.runtime
    cfg = getattr(state, "config", {}) or {}
    keys = _load_keys(cfg)
    if not keys:
        return "dev"

    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not key:
        raise HTTPException(status_code=401, detail={"status": "UNAUTHORIZED", "reason": "missing_api_key"})

    for k in keys:
        if key == k.key:
            request.state.role = k.role
            return k.role

    raise HTTPException(status_code=403, detail={"status": "FORBIDDEN", "reason": "invalid_api_key"})
