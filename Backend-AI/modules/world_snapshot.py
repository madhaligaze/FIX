import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_SNAPSHOT_DIR = "/tmp/ai_brain_snapshots"


def _stable_json(obj: Any) -> str:
    """Deterministic JSON encoding used for revision hashing."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_revision(session_dict: Dict[str, Any]) -> str:
    """Compute a stable-ish hash for the current world state.

    This is for reproducibility and UI, not for security.
    We intentionally hash only a compact projection of the session.
    """
    scene = session_dict.get("scene_context") or {}
    payload = {
        "frames": len(session_dict.get("frames") or []),
        "anchors": len(scene.get("anchor_points") or []),
        "ar_points": len(scene.get("all_ar_points") or []),
        "detected_objects": len(scene.get("all_detected_objects") or []),
        "point_cloud": len(scene.get("point_cloud") or []),
    }
    blob = _stable_json(payload).encode("utf-8")
    return hashlib.sha1(blob).hexdigest()[:16]


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _gzip_write_json(path: Path, data: Any) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        f.write(_stable_json(data))


def _gzip_read_json(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.loads(f.read())


def _encode_voxel_world(voxel_world: Any) -> Dict[str, Any]:
    """Serialize voxel world into a compact dict.

    Current project uses a sparse set of occupied voxels.
    """
    if voxel_world is None:
        return {"present": False}

    # occupied voxels + type map if exists
    occupied = []
    types = getattr(voxel_world, "_types", None)
    for ijk in getattr(voxel_world, "occupied", []) or []:
        t = None
        if isinstance(types, dict):
            t = types.get(ijk)
        occupied.append([int(ijk[0]), int(ijk[1]), int(ijk[2]), int(t) if t is not None else None])

    return {
        "present": True,
        "resolution": float(getattr(voxel_world, "resolution", 0.1)),
        "occupied": occupied,
    }


def _decode_voxel_world(payload: Dict[str, Any]) -> Any:
    if not payload or not payload.get("present"):
        return None

    try:
        from modules.voxel_world import VoxelWorld

        vw = VoxelWorld(resolution=float(payload.get("resolution", 0.1)))
        for item in payload.get("occupied") or []:
            if len(item) < 3:
                continue
            ijk = (int(item[0]), int(item[1]), int(item[2]))
            vw.occupied.add(ijk)
            if len(item) >= 4 and item[3] is not None:
                try:
                    vw._types[ijk] = int(item[3])
                    vw._grid[ijk] = int(item[3])
                except Exception:
                    pass
        return vw
    except Exception:
        return None


def snapshot_path(session_id: str, revision: str, base_dir: str = DEFAULT_SNAPSHOT_DIR) -> Path:
    return Path(base_dir) / session_id / revision


def save_snapshot(
    session_dict: Dict[str, Any],
    voxel_world: Any,
    base_dir: str = DEFAULT_SNAPSHOT_DIR,
    revision: Optional[str] = None,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Save a reproducible snapshot of the world model and context."""

    if revision is None:
        revision = compute_revision(session_dict)

    root = snapshot_path(session_dict.get("session_id", "unknown"), revision, base_dir=base_dir)
    _ensure_dir(root)

    meta = {
        "session_id": session_dict.get("session_id"),
        "revision": revision,
        "created_at": time.time(),
        "reason": reason,
        "counts": {
            "frames": len(session_dict.get("frames") or []),
            "anchors": len((session_dict.get("scene_context") or {}).get("anchor_points") or []),
            "detected_objects": len((session_dict.get("scene_context") or {}).get("all_detected_objects") or []),
            "voxels": len(getattr(voxel_world, "occupied", []) or []),
        },
    }

    (root / "meta.json").write_text(_stable_json(meta), encoding="utf-8")

    # session context (frames are already truncated in Session.to_dict())
    _gzip_write_json(root / "session.json.gz", session_dict)

    # voxel world
    vw_payload = _encode_voxel_world(voxel_world)
    _gzip_write_json(root / "voxel_world.json.gz", vw_payload)

    return meta


def list_snapshots(session_id: str, base_dir: str = DEFAULT_SNAPSHOT_DIR) -> List[Dict[str, Any]]:
    root = Path(base_dir) / session_id
    if not root.exists() or not root.is_dir():
        return []
    out: List[Dict[str, Any]] = []
    for rev_dir in sorted(root.iterdir()):
        meta_path = rev_dir / "meta.json"
        if meta_path.exists():
            try:
                out.append(json.loads(meta_path.read_text(encoding="utf-8")))
            except Exception:
                continue
    # newest first
    out.sort(key=lambda x: float(x.get("created_at", 0)), reverse=True)
    return out


def load_snapshot(
    session_id: str,
    revision: str,
    base_dir: str = DEFAULT_SNAPSHOT_DIR,
) -> Tuple[Optional[Dict[str, Any]], Any]:
    root = snapshot_path(session_id, revision, base_dir=base_dir)
    if not root.exists():
        return None, None

    session_dict = _gzip_read_json(root / "session.json.gz")
    vw_payload = _gzip_read_json(root / "voxel_world.json.gz")
    vw = _decode_voxel_world(vw_payload)
    return session_dict, vw
