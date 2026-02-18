from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from session.artifacts import ensure_dirs, save_bytes, save_json


class SessionStore:
    def __init__(self, artifacts_root: str = "sessions") -> None:
        self.root = ensure_dirs(Path(artifacts_root))

    def create_session(self) -> str:
        session_id = str(uuid4())
        ensure_dirs(self.root / session_id)
        return session_id

    def session_root(self, session_id: str) -> Path:
        return self.root / session_id

    def save_frame(
        self,
        session_id: str,
        frame_id: str,
        meta: dict[str, Any],
        rgb_bytes: bytes,
        depth_bytes: bytes | None = None,
        pointcloud_bytes: bytes | None = None,
    ) -> None:
        base = ensure_dirs(self.session_root(session_id) / "frames" / frame_id)
        save_json(base / "meta.json", meta)
        save_bytes(base / "rgb.jpg", rgb_bytes)
        if depth_bytes is not None:
            save_bytes(base / "depth.u16", depth_bytes)
        if pointcloud_bytes is not None:
            save_bytes(base / "pointcloud.npy", pointcloud_bytes)

    def save_anchors(self, session_id: str, anchors: list[dict[str, Any]]) -> None:
        save_json(self.session_root(session_id) / "anchors" / "anchors.json", anchors)

    def lock_revision(
        self,
        session_id: str,
        world_model_state: dict[str, Any],
        overlays: dict[str, Any],
        trace: list[dict[str, Any]],
        env_mesh_bytes: bytes | None = None,
    ) -> str:
        rev_id = str(uuid4())
        base = ensure_dirs(self.session_root(session_id) / "world" / rev_id)
        save_json(base / "world_state.json", world_model_state)
        save_json(base / "overlays.json", overlays)
        save_json(base / "trace.json", trace)
        if env_mesh_bytes:
            save_bytes(base / "env_mesh.obj", env_mesh_bytes)
        return rev_id

    def save_export(self, session_id: str, rev_id: str, scene_bundle: dict[str, Any]) -> Path:
        path = self.session_root(session_id) / "exports" / rev_id / "scene_bundle.json"
        save_json(path, scene_bundle)
        latest = self.session_root(session_id) / "exports" / "latest.json"
        save_json(latest, {"rev_id": rev_id})
        return path

    def load_export(self, session_id: str, rev_id: str) -> dict[str, Any]:
        import json

        path = self.session_root(session_id) / "exports" / rev_id / "scene_bundle.json"
        return json.loads(path.read_text(encoding="utf-8"))
