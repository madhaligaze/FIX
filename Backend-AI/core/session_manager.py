import json
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class CameraFrame:
    timestamp: float
    image_data: str = ""
    camera_position: List[float] = field(default_factory=list)
    ar_points: List[Dict[str, Any]] = field(default_factory=list)
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    detected_objects: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CameraFrame":
        return cls(**data)


class SceneContext:
    def __init__(self) -> None:
        self.anchor_points: List[Dict[str, Any]] = []
        self.all_ar_points: List[Dict[str, Any]] = []
        self.all_detected_objects: List[Dict[str, Any]] = []
        self.point_cloud: List[Dict[str, Any]] = []
        self.obstacles: List[Dict[str, Any]] = []
        self.voxel_world = None

    def ensure_voxel_world(self):
        if self.voxel_world is None:
            try:
                from modules.voxel_world import VoxelWorld

                self.voxel_world = VoxelWorld()
            except Exception:
                self.voxel_world = None
        return self.voxel_world

    def ingest_frame(self, frame: CameraFrame) -> None:
        if frame.ar_points:
            self.anchor_points.extend(frame.ar_points)
            self.all_ar_points.extend(frame.ar_points)
        if frame.detected_objects:
            self.all_detected_objects.extend(frame.detected_objects)
        point_cloud = frame.quality_metrics.get("point_cloud") if frame.quality_metrics else None
        if point_cloud:
            self.point_cloud.extend(point_cloud)

    def get_summary(self) -> Dict[str, Any]:
        return {
            "anchors": len(self.anchor_points),
            "ar_points": len(self.all_ar_points),
            "detected_objects": len(self.all_detected_objects),
            "point_cloud_points": len(self.point_cloud),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anchor_points": self.anchor_points,
            "all_ar_points": self.all_ar_points,
            "all_detected_objects": self.all_detected_objects,
            "point_cloud": self.point_cloud,
            "obstacles": self.obstacles,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneContext":
        ctx = cls()
        ctx.anchor_points = data.get("anchor_points", [])
        ctx.all_ar_points = data.get("all_ar_points", [])
        ctx.all_detected_objects = data.get("all_detected_objects", [])
        ctx.point_cloud = data.get("point_cloud", [])
        ctx.obstacles = data.get("obstacles", [])
        return ctx


class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.status = "ACTIVE"
        self.frames: List[CameraFrame] = []
        self.scene_context = SceneContext()
        self.generated_variants: List[Dict[str, Any]] = []
        self.current_structure: List[Dict[str, Any]] = []
        self.user_anchors: List[Dict[str, Any]] = []
        self._structural_graph = None

    def add_frame(self, frame: CameraFrame) -> None:
        self.frames.append(frame)
        self.scene_context.ingest_frame(frame)
        if frame.ar_points:
            self.user_anchors.extend(frame.ar_points)
        self.updated_at = time.time()

    def add_variant(self, variant: Dict[str, Any]) -> None:
        self.generated_variants.append(variant)
        self.updated_at = time.time()

    def save_structure(self, elements: List[Dict[str, Any]]) -> None:
        self.current_structure = elements
        self.updated_at = time.time()

    def remove_element(self, element_id: str) -> bool:
        before = len(self.current_structure)
        self.current_structure = [el for el in self.current_structure if el.get("id") != element_id]
        changed = len(self.current_structure) != before
        if changed:
            self.updated_at = time.time()
        return changed

    def add_element(self, element_data: Dict[str, Any]) -> None:
        self.current_structure.append(element_data)
        self.updated_at = time.time()

    def ensure_structural_graph(self):
        if self._structural_graph is None:
            try:
                from modules.structural_graph import StructuralGraph

                self._structural_graph = StructuralGraph()
            except Exception:
                self._structural_graph = None
        return self._structural_graph

    def get_context_summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "frames": len(self.frames),
            "variants": len(self.generated_variants),
            "current_structure_elements": len(self.current_structure),
            "scene": self.scene_context.get_summary(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "frames": [f.to_dict() for f in self.frames[-200:]],
            "scene_context": self.scene_context.to_dict(),
            "generated_variants": self.generated_variants,
            "current_structure": self.current_structure,
            "user_anchors": self.user_anchors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        s = cls(data["session_id"])
        s.created_at = data.get("created_at", s.created_at)
        s.updated_at = data.get("updated_at", s.updated_at)
        s.status = data.get("status", "ACTIVE")
        s.frames = [CameraFrame.from_dict(item) for item in data.get("frames", [])]
        s.scene_context = SceneContext.from_dict(data.get("scene_context", {}))
        s.generated_variants = data.get("generated_variants", [])
        s.current_structure = data.get("current_structure", [])
        s.user_anchors = data.get("user_anchors", [])
        return s


class SessionManager:
    def __init__(self, base_dir: str = "/tmp/ai_brain_sessions"):
        self.sessions: Dict[str, Session] = {}
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_session(self) -> str:
        session_id = f"session_{uuid4().hex[:10]}"
        self.sessions[session_id] = Session(session_id)
        self.auto_save_session(session_id)
        return session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        session = self.sessions.get(session_id)
        if session:
            return session
        loaded = self.load_from_disk(session_id)
        if loaded:
            self.sessions[session_id] = loaded
        return loaded

    def delete_session(self, session_id: str) -> bool:
        removed = self.sessions.pop(session_id, None) is not None
        session_dir = self.base_dir / session_id
        if session_dir.exists():
            for path in session_dir.glob("*"):
                path.unlink(missing_ok=True)
            session_dir.rmdir()
            removed = True
        return removed

    def export_session_data(self, session_id: str) -> Dict[str, Any]:
        session = self.get_session(session_id)
        if not session:
            return {}
        return session.to_dict()

    def save_to_disk(self, session: Session) -> bool:
        session_dir = self.base_dir / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        metadata = {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "status": session.status,
        }
        (session_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        (session_dir / "current_structure.json").write_text(
            json.dumps(session.current_structure, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (session_dir / "point_cloud.json").write_text(
            json.dumps(session.scene_context.point_cloud, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (session_dir / "history.json").write_text(
            json.dumps(
                {
                    "frames": [f.to_dict() for f in session.frames[-200:]],
                    "generated_variants": session.generated_variants,
                    "scene_context": session.scene_context.to_dict(),
                    "user_anchors": session.user_anchors,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return True

    def load_from_disk(self, session_id: str) -> Optional[Session]:
        session_dir = self.base_dir / session_id
        metadata_path = session_dir / "metadata.json"
        history_path = session_dir / "history.json"
        structure_path = session_dir / "current_structure.json"

        if not metadata_path.exists() or not history_path.exists():
            return None

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        history = json.loads(history_path.read_text(encoding="utf-8"))
        structure = []
        if structure_path.exists():
            structure = json.loads(structure_path.read_text(encoding="utf-8"))

        payload = {
            **metadata,
            "frames": history.get("frames", []),
            "scene_context": history.get("scene_context", {}),
            "generated_variants": history.get("generated_variants", []),
            "current_structure": structure,
            "user_anchors": history.get("user_anchors", []),
        }
        return Session.from_dict(payload)

    def auto_save_session(self, session_id: str) -> bool:
        session = self.sessions.get(session_id)
        if not session:
            return False
        try:
            return self.save_to_disk(session)
        except Exception:
            return False

    def restore_sessions(self) -> int:
        restored = 0
        for entry in self.base_dir.glob("session_*"):
            if not entry.is_dir():
                continue
            session = self.load_from_disk(entry.name)
            if session:
                self.sessions[entry.name] = session
                restored += 1
        return restored


session_manager = SessionManager()
