import json
import time
from dataclasses import asdict, dataclass, field
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
        self.tsdf_integrator = None

    def ensure_voxel_world(self):
        if self.voxel_world is None:
            try:
                from modules.voxel_world import VoxelWorld

                self.voxel_world = VoxelWorld()
            except Exception:
                self.voxel_world = None
        return self.voxel_world

    def ensure_tsdf_integrator(self):
        if self.tsdf_integrator is None:
            try:
                from modules.tsdf_integrator import TSDFIntegrator

                self.tsdf_integrator = TSDFIntegrator()
            except Exception:
                self.tsdf_integrator = None
        return self.tsdf_integrator

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
        self.last_activity = self.created_at
        self.status = "ACTIVE"
        self.frames: List[CameraFrame] = []
        self.scene_context = SceneContext()
        self.generated_variants: List[Dict[str, Any]] = []
        self.current_structure: List[Dict[str, Any]] = []
        self.structure_history: List[Dict[str, Any]] = []
        self.user_anchors: List[Dict[str, Any]] = []
        self.total_frames_processed = 0
        self.total_objects_detected = 0
        self._structural_graph = None

    def _touch(self) -> None:
        now = time.time()
        self.updated_at = now
        self.last_activity = now

    def add_frame(self, frame: CameraFrame) -> None:
        self.frames.append(frame)
        self.scene_context.ingest_frame(frame)
        if frame.ar_points:
            self.user_anchors.extend(frame.ar_points)
        self.total_frames_processed += 1
        self.total_objects_detected += len(frame.detected_objects)
        self._touch()

    def add_variant(self, variant: Dict[str, Any]) -> None:
        self.generated_variants.append(variant)
        self._touch()

    def save_structure(self, elements: List[Dict[str, Any]]) -> None:
        self.current_structure = elements
        self.structure_history.append(
            {
                "timestamp": time.time(),
                "action": "SAVE_STRUCTURE",
                "elements_count": len(elements),
            }
        )
        self._touch()

    def remove_element(self, element_id: str) -> bool:
        before = len(self.current_structure)
        self.current_structure = [el for el in self.current_structure if el.get("id") != element_id]
        changed = len(self.current_structure) != before
        if changed:
            self.structure_history.append(
                {
                    "timestamp": time.time(),
                    "action": "REMOVE",
                    "element_id": element_id,
                    "elements_count": len(self.current_structure),
                }
            )
            self._touch()
        return changed

    def add_element(self, element_data: Dict[str, Any]) -> None:
        self.current_structure.append(element_data)
        self.structure_history.append(
            {
                "timestamp": time.time(),
                "action": "ADD",
                "element_id": element_data.get("id"),
                "elements_count": len(self.current_structure),
            }
        )
        self._touch()

    def is_expired(self, timeout_seconds: int) -> bool:
        return (time.time() - self.last_activity) > timeout_seconds

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
            "last_activity": self.last_activity,
            "total_frames_processed": self.total_frames_processed,
            "total_objects_detected": self.total_objects_detected,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activity": self.last_activity,
            "status": self.status,
            "frames": [f.to_dict() for f in self.frames[-200:]],
            "scene_context": self.scene_context.to_dict(),
            "generated_variants": self.generated_variants,
            "current_structure": self.current_structure,
            "structure_history": self.structure_history,
            "user_anchors": self.user_anchors,
            "total_frames_processed": self.total_frames_processed,
            "total_objects_detected": self.total_objects_detected,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        s = cls(data["session_id"])
        s.created_at = data.get("created_at", s.created_at)
        s.updated_at = data.get("updated_at", s.updated_at)
        s.last_activity = data.get("last_activity", s.updated_at)
        s.status = data.get("status", "ACTIVE")
        s.frames = [CameraFrame.from_dict(item) for item in data.get("frames", [])]
        s.scene_context = SceneContext.from_dict(data.get("scene_context", {}))
        s.generated_variants = data.get("generated_variants", [])
        s.current_structure = data.get("current_structure", [])
        s.structure_history = data.get("structure_history", [])
        s.user_anchors = data.get("user_anchors", [])
        s.total_frames_processed = data.get("total_frames_processed", len(s.frames))
        s.total_objects_detected = data.get("total_objects_detected", len(s.scene_context.all_detected_objects))
        return s

    def save_to_disk(self, base_dir: str = "/tmp/ai_brain_sessions") -> bool:
        """Сохранить сессию на диск."""
        try:
            session_dir = Path(base_dir) / self.session_id
            session_dir.mkdir(parents=True, exist_ok=True)

            metadata = {
                "session_id": self.session_id,
                "created_at": self.created_at,
                "last_activity": self.last_activity,
                "updated_at": self.updated_at,
                "status": self.status,
                "total_frames_processed": self.total_frames_processed,
                "total_objects_detected": self.total_objects_detected,
            }
            with open(session_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            if self.current_structure:
                with open(session_dir / "current_structure.json", "w", encoding="utf-8") as f:
                    json.dump(self.current_structure, f, indent=2, ensure_ascii=False)

            if self.scene_context.point_cloud:
                with open(session_dir / "point_cloud.json", "w", encoding="utf-8") as f:
                    json.dump(self.scene_context.point_cloud, f, indent=2, ensure_ascii=False)

            history_payload = {
                "frames": [f.to_dict() for f in self.frames[-200:]],
                "generated_variants": self.generated_variants,
                "scene_context": self.scene_context.to_dict(),
                "user_anchors": self.user_anchors,
                "structure_history": self.structure_history,
            }
            with open(session_dir / "history.json", "w", encoding="utf-8") as f:
                json.dump(history_payload, f, indent=2, ensure_ascii=False)

            print(f"✓ Session {self.session_id} saved to disk")
            return True
        except Exception as e:
            print(f"✗ Failed to save session: {e}")
            return False

    @classmethod
    def load_from_disk(cls, session_id: str, base_dir: str = "/tmp/ai_brain_sessions") -> Optional["Session"]:
        """Загрузить сессию с диска."""
        try:
            session_dir = Path(base_dir) / session_id
            if not session_dir.exists():
                return None

            with open(session_dir / "metadata.json", "r", encoding="utf-8") as f:
                metadata = json.load(f)

            session = cls(session_id=session_id)
            session.created_at = metadata.get("created_at", session.created_at)
            session.updated_at = metadata.get("updated_at", session.updated_at)
            session.last_activity = metadata.get("last_activity", session.updated_at)
            session.status = metadata.get("status", "ACTIVE")
            session.total_frames_processed = metadata.get("total_frames_processed", 0)
            session.total_objects_detected = metadata.get("total_objects_detected", 0)

            structure_file = session_dir / "current_structure.json"
            if structure_file.exists():
                with open(structure_file, "r", encoding="utf-8") as f:
                    session.current_structure = json.load(f)

            pc_file = session_dir / "point_cloud.json"
            if pc_file.exists():
                with open(pc_file, "r", encoding="utf-8") as f:
                    session.scene_context.point_cloud = json.load(f)

            history_file = session_dir / "history.json"
            if history_file.exists():
                with open(history_file, "r", encoding="utf-8") as f:
                    history_data = json.load(f)
                session.frames = [CameraFrame.from_dict(item) for item in history_data.get("frames", [])]
                session.generated_variants = history_data.get("generated_variants", [])
                session.scene_context = SceneContext.from_dict(history_data.get("scene_context", {}))
                session.user_anchors = history_data.get("user_anchors", [])
                session.structure_history = history_data.get("structure_history", [])

            print(f"✓ Session {session_id} loaded from disk")
            return session
        except Exception as e:
            print(f"✗ Failed to load session: {e}")
            return None


class SessionManager:
    def __init__(self, base_dir: str = "/tmp/ai_brain_sessions", session_timeout: int = 60 * 60 * 12):
        self.sessions: Dict[str, Session] = {}
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.session_timeout = session_timeout

    def create_session(self) -> str:
        session_id = f"session_{uuid4().hex[:10]}"
        self.sessions[session_id] = Session(session_id)
        self.auto_save_session(session_id)
        return session_id

    def get_session(self, session_id: str) -> Optional[Session]:
        """Получить сессию (сначала из RAM, потом с диска)."""
        session = self.sessions.get(session_id)
        if session:
            if session.is_expired(self.session_timeout):
                self.delete_session(session_id)
                return None
            return session

        session = Session.load_from_disk(session_id, base_dir=str(self.base_dir))
        if session:
            if session.is_expired(self.session_timeout):
                self.delete_session(session_id)
                return None
            self.sessions[session_id] = session
            return session
        return None

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
        return session.save_to_disk(str(self.base_dir))

    def load_from_disk(self, session_id: str) -> Optional[Session]:
        return Session.load_from_disk(session_id, base_dir=str(self.base_dir))

    def auto_save_session(self, session_id: str) -> bool:
        """Автосохранение сессии на диск."""
        session = self.sessions.get(session_id)
        if session:
            return session.save_to_disk(str(self.base_dir))
        return False

    def restore_sessions(self) -> int:
        restored = 0
        for entry in self.base_dir.glob("session_*"):
            if not entry.is_dir():
                continue
            session = self.load_from_disk(entry.name)
            if session and not session.is_expired(self.session_timeout):
                self.sessions[entry.name] = session
                restored += 1
        return restored


session_manager = SessionManager()
