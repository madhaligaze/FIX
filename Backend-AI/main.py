"""
Main FastAPI Server - AI Brain Backend
=======================================
СТАТУС: Production Ready

Интеграция всех исправленных модулей:
✓ LayherStandards - правильные размеры
✓ PhysicsEnhanced - Closed Loop оптимизация
✓ CollisionSolver - умное решение коллизий
✓ BuilderFixed - генератор с валидацией
✓ SessionManager - контекст всей сцены
"""
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import base64
import time
import traceback
import json
import logging

# Импорты исправленных модулей
from modules.layher_standards import (
    LayherStandards,
    BillOfMaterials,
)
from modules.geometry import (
    validate_dimensions,
    snap_to_grid,
)
from modules.physics import PhysicsEngine, quick_safety_check
from modules.voxel_world import VoxelCollisionSolver
from modules.builder import ScaffoldGenerator
from modules.session_manager import CameraFrame
from modules.session import SessionManager
from modules.monitoring import request_logger, performance_monitor
from modules.cache_manager import global_cache
from modules.validators import SessionUpdateAction, validate_session_exists, validate_structure_stability

# ── Новые модули v3.0 ───────────────────────────────────────────────────────
try:
    from modules.astar_pathfinder import ScaffoldPathfinder
    from modules.auto_scaffolder import AutoScaffolder
    from modules.post_processor import StructuralPostProcessor

    BRAIN_V3_AVAILABLE = True
except ImportError:
    BRAIN_V3_AVAILABLE = False


# ── Новые модули v4.0 ───────────────────────────────────────────────────────
from modules.mesher import PointCloudProcessor
from modules.mesh_builder import ScaffoldMeshBuilder
from modules.exporter import BOMExporter
from modules.inspector import ScaffoldInspector
from modules.debug_dumper import DebugDumper

# ═══════════════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="AI Brain - Scaffolding Intelligence",
    version="4.0.0",
    description="Генеративный инжиниринг строительных лесов с Layher стандартами"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("ai_brain.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)



@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Логировать HTTP запросы и время ответа."""
    start_time = time.time()
    session_id = request.path_params.get("session_id") if hasattr(request, "path_params") else None

    try:
        response = await call_next(request)
        duration = time.time() - start_time
        request_logger.log_request(
            method=request.method,
            path=request.url.path,
            duration=duration,
            status_code=response.status_code,
            session_id=session_id,
        )
        response.headers["X-Process-Time"] = f"{duration:.4f}"
        return response
    except Exception as exc:
        duration = time.time() - start_time
        request_logger.log_request(
            method=request.method,
            path=request.url.path,
            duration=duration,
            status_code=500,
            session_id=session_id,
            error=str(exc),
        )
        raise

# CORS для Android приложения
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализация компонентов
scaffold_generator = ScaffoldGenerator()
physics_engine = PhysicsEngine()
collision_solver = VoxelCollisionSolver(clearance=0.15)

# Инициализация глобального менеджера сессий
session_manager = SessionManager()


# v4.0 components
point_cloud_processor = PointCloudProcessor()
mesh_builder = ScaffoldMeshBuilder()
bom_exporter = BOMExporter()
scaffold_inspector = ScaffoldInspector()
debug_dumper = DebugDumper()

# Session persistence: восстанавливаем сессии после рестарта процесса
session_manager.restore_sessions()


def _normalize_camera_pose(camera_pose: Optional[List[float]]) -> List[float]:
    """Нормализация camera_pose до формата [tx,ty,tz,qx,qy,qz,qw]."""
    if not camera_pose:
        return [0, 0, 0, 0, 0, 0, 1]

    cp = list(camera_pose)
    if len(cp) >= 7:
        return cp[:7]

    if len(cp) == 6:
        # Часто с Android приходит только position + euler, пока принимаем как identity quaternion.
        return [cp[0], cp[1], cp[2], 0, 0, 0, 1]

    return [0, 0, 0, 0, 0, 0, 1]


def _build_layher_bom_from_elements(elements: List[Dict[str, Any]]) -> BillOfMaterials:
    """Формирует BOM Layher из full_structure/elements."""
    bom = BillOfMaterials()

    for el in elements:
        etype = (el.get('type') or 'ledger').lower()
        length = float(el.get('length', 0) or 0)

        if etype in ('standard', 'vertical'):
            std_length = LayherStandards.get_nearest_standard_height(length)
            code = f"S-{int(std_length * 100)}"
        elif etype in ('ledger', 'transom'):
            std_length = LayherStandards.get_nearest_ledger_length(length)
            code = f"L-{int(std_length * 100)}"
        elif etype == 'diagonal':
            std_length = min(LayherStandards.DIAGONAL_LENGTHS, key=lambda x: abs(x - length))
            code = f"D-{int(std_length * 100)}"
        elif etype == 'deck':
            deck_len = LayherStandards.get_nearest_deck_length(length)
            code = LayherStandards.DECK_ARTICLES.get(deck_len, f"P-{int(deck_len * 100)}")
        else:
            code = 'UNKNOWN'

        bom.add_component(code, 1)

    return bom

# v3.2: PostProcessor для диагоналей и настилов
if BRAIN_V3_AVAILABLE:
    post_processor = StructuralPostProcessor()


# ═══════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════

class SessionStartRequest(BaseModel):
    """Запрос на создание сессии"""
    user_id: Optional[str] = None
    project_name: Optional[str] = "Unnamed Project"


class SessionStartResponse(BaseModel):
    """Ответ при создании сессии"""
    session_id: str
    message: str
    timestamp: float


class Point3D(BaseModel):
    """3D точка"""
    x: float
    y: float
    z: float = 0.0


class DetectedObject(BaseModel):
    """Обнаруженный объект"""
    type: str  # "wall", "pipe", "column", etc.
    position: Point3D
    dimensions: Optional[Dict[str, float]] = None
    confidence: float = 1.0


class StreamFrameRequest(BaseModel):
    """Запрос на стриминг кадра (legacy wrapper for FramePacket).

    ВНИМАНИЕ:
      - Для честного 2D->3D lifting нужны intrinsics + pose + (depth или point_cloud).
      - Если этих полей нет, endpoint работает как legacy: только point_cloud -> VoxelWorld, без vision.
      - Рекомендуемый endpoint: POST /session/frame (FramePacketRequest).
    """

    session_id: str

    # Legacy: base64 encoded image (jpeg/png)
    frame_base64: str

    # Legacy: optional (Android used to send only position)
    camera_position: Optional[Dict] = None

    # Legacy: user anchor points
    ar_points: List[Point3D] = []

    # Legacy: point cloud in world coords (ARCore already transformed).
    # Format: [[x, y, z, confidence], ...] or [[x, y, z], ...]
    point_cloud: List[List[float]] = []

    timestamp: Optional[float] = None

    # ── Optional FramePacket fields (recommended to send) ──────────────────
    frame_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fx: Optional[float] = None
    fy: Optional[float] = None
    cx_px: Optional[float] = None
    cy_px: Optional[float] = None
    pose_world_from_camera: Optional[List[float]] = None
    depth_base64: Optional[str] = None
    depth_scale: float = 1000.0
    confidence_base64: Optional[str] = None
    enable_vision: bool = True


class GenerateRequest(BaseModel):
    """Запрос на генерацию вариантов"""
    session_id: str
    target_dimensions: Dict[str, float]  # {width, height, depth}
    user_points: List[Point3D] = []
    use_ai_detection: bool = True
    optimize_structure: bool = True  # Включить Closed Loop оптимизацию
    planner_mode: str = "beam"  # legacy|beam
    max_variants: int = 3
    unknown_policy: str = "forbid"  # forbid|buffer
    # НОВОЕ: если задан — используем AutoScaffolder вместо старого генератора.
    # Формат: {"x": f, "y": f, "z": f} — точка доступа (труба/оборудование на потолке).
    target_point: Optional[Point3D] = None


class AnalyzeRequest(BaseModel):
    """Запрос на физический анализ"""
    nodes: List[Dict]
    beams: List[Dict]
    fixed_node_ids: Optional[List[str]] = None
    optimize_if_critical: bool = True  # Авто-оптимизация при перегрузке


class ExportBOMRequest(BaseModel):
    """Запрос на экспорт спецификации"""
    session_id: str
    variant_index: int


# ─── v3.0 Models ────────────────────────────────────────────────────────────

class DepthStreamRequest(BaseModel):
    """Стриминг карты глубины с ARCore Depth API."""

    session_id: str
    depth_base64: str
    width: int
    height: int
    fx: float = 500.0
    fy: float = 500.0
    cx_px: float = 320.0
    cy_px: float = 240.0
    camera_pose: List[float] = [0, 0, 0, 0, 0, 0, 1]
    depth_scale: float = 1000.0
    confidence_base64: Optional[str] = None
    confidence_threshold: int = 1
    pixel_step: int = 4




class Intrinsics(BaseModel):
    fx: float
    fy: float
    cx: float
    cy: float
    width: int
    height: int


class FramePacketRequest(BaseModel):
    """
    FramePacket (Stage 2+): keyframe payload for honest 2D->3D.

    Required for 3D lifting:
      - intrinsics (fx,fy,cx,cy + image size)
      - pose_world_from_camera (tx,ty,tz,qx,qy,qz,qw)
      - rgb (bytes/base64)
      - depth OR point_cloud fallback
    """

    session_id: str
    frame_id: str
    timestamp: Optional[float] = None

    # RGB image (base64-encoded bytes, jpeg/png)
    rgb_base64: str

    # Image size
    width: int
    height: int

    # Intrinsics
    fx: float
    fy: float
    cx_px: float
    cy_px: float

    # Pose: [tx,ty,tz,qx,qy,qz,qw] world_from_camera
    pose_world_from_camera: List[float]

    # Depth (optional)
    depth_base64: Optional[str] = None
    depth_scale: float = 1000.0
    confidence_base64: Optional[str] = None

    # Point cloud fallback (world coords)
    point_cloud: List[List[float]] = []

    # Enable / disable vision (2D detector + lifting)
    enable_vision: bool = True


class LockWorldRequest(BaseModel):
    session_id: str

class StructureModifyRequest(BaseModel):
    """Интерактивное изменение конструкции (удалить/добавить элемент)"""

    session_id: str
    action: str
    element_id: Optional[str] = None
    element_data: Optional[Dict] = None


class AutoScaffoldRequest(BaseModel):
    """Автоматическая сборка от целевой точки"""

    session_id: str
    target: Point3D
    clearance_box: Optional[Dict] = None
    floor_z: float = 0.0
    ledger_len: float = 1.09
    standard_h: float = 2.07


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Корневой endpoint - информация о сервере"""
    return {
        "name": "AI Brain Backend",
        "version": "4.0.0",
        "status": "operational",
        "features": {
            "layher_standards": True,
            "closed_loop_optimization": True,
            "collision_avoidance": True,
            "session_context": True,
            "physics_validation": True
        },
        "standards": {
            "ledger_lengths": LayherStandards.LEDGER_LENGTHS,
            "standard_heights": LayherStandards.STANDARD_HEIGHTS
        }
    }


@app.get("/health")
async def health_check():
    """Health check для мониторинга"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "active_sessions": len(session_manager.sessions),
        "uptime_seconds": time.time()  # Упрощенно
    }


@app.post("/session/start")
async def start_session(request: SessionStartRequest):
    """
    Создание новой сессии.
    
    Android должен вызвать этот endpoint перед началом работы.
    """
    try:
        session_id = session_manager.create_session()
        
        return SessionStartResponse(
            session_id=session_id,
            message="Сессия создана успешно. ИИ готов к работе.",
            timestamp=time.time()
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@app.post("/session/frame")
async def ingest_frame_packet(request: FramePacketRequest):
    """
    Stage 2: Honest vision integration (2D -> 3D lifting + stable WorldObjects).

    - Updates world geometry from depth / point cloud.
    - Runs optional 2D detector.
    - Lifts Det2D -> Det3D using intrinsics + pose + depth (or point cloud fallback).
    - Tracks & fuses into stable world_objects in session.scene_context.
    """
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Сессия не найдена")

        # Decode RGB
        rgb_bytes = base64.b64decode(request.rgb_base64)

        # Decode optional depth/conf
        depth_bytes = base64.b64decode(request.depth_base64) if request.depth_base64 else None
        conf_bytes = base64.b64decode(request.confidence_base64) if request.confidence_base64 else None

        # Ensure world models
        voxel_world = session.scene_context.ensure_voxel_world()
        tsdf = session.scene_context.ensure_tsdf_integrator()

        # Geometry integration
        geom_stats = {}
        if voxel_world is not None and depth_bytes is not None:
            try:
                normalized_pose = _normalize_camera_pose(request.pose_world_from_camera)

                stats = voxel_world.ingest_depth_map(
                    depth_bytes=depth_bytes,
                    width=request.width,
                    height=request.height,
                    fx=request.fx,
                    fy=request.fy,
                    cx_px=request.cx_px,
                    cy_px=request.cy_px,
                    camera_pose=normalized_pose,
                    depth_scale=request.depth_scale,
                    confidence_bytes=conf_bytes,
                    confidence_threshold=1,
                    pixel_step=4,
                )
                geom_stats.update(stats or {})
                # Coverage/unknown quality metrics (Stage 1)
                geom_stats.update(voxel_world.get_coverage_metrics())
            except Exception as e:
                geom_stats["depth_ingest_error"] = str(e)

        elif voxel_world is not None and request.point_cloud:
            try:
                added = voxel_world.add_point_cloud(request.point_cloud)
                geom_stats["voxels_added"] = int(added)
                geom_stats["total_voxels"] = int(voxel_world.total_voxels)
            except Exception as e:
                geom_stats["point_cloud_ingest_error"] = str(e)

        # TSDF integration for mesh (optional)
        mesh_info = {}
        if tsdf is not None and depth_bytes is not None:
            try:
                import numpy as np
                from modules.lifter_2d3d import decode_depth_bytes, decode_confidence_bytes

                depth_arr = decode_depth_bytes(depth_bytes, request.width, request.height)
                conf_arr = decode_confidence_bytes(conf_bytes, request.width, request.height) if conf_bytes else None
                # TSDFIntegrator expects depth in meters and (optionally) confidence weights
                # Convert to meters for TSDF
                depth_meters = depth_arr.astype(np.float32) / float(request.depth_scale)
                tsdf.integrate_depth(
                    depth_m=depth_meters,
                    fx=request.fx,
                    fy=request.fy,
                    cx=request.cx_px,
                    cy=request.cy_px,
                    pose_world_from_camera_7=tuple(_normalize_camera_pose(request.pose_world_from_camera)),
                    depth_trunc=None,
                )
                mesh_info["tsdf_integrated"] = True
            except Exception as e:
                mesh_info["tsdf_integrated"] = False
                mesh_info["tsdf_error"] = str(e)

        # Perception pipeline
        det2d, det3d, world_objects = [], [], []
        scan_suggestions = []
        pb = session.scene_context.ensure_perception_backend()
        if pb is not None:
            out = pb.process_frame(
                frame_id=request.frame_id,
                rgb_bytes=rgb_bytes,
                width=request.width,
                height=request.height,
                fx=request.fx,
                fy=request.fy,
                cx=request.cx_px,
                cy=request.cy_px,
                pose7=_normalize_camera_pose(request.pose_world_from_camera),
                depth_bytes=depth_bytes,
                depth_scale=request.depth_scale,
                conf_bytes=conf_bytes,
                point_cloud_world=request.point_cloud if request.point_cloud else None,
                voxel_world=voxel_world,
                enable_vision=bool(request.enable_vision),
            )
            det2d = out.get("det2d", [])
            det3d = out.get("det3d", [])
            world_objects = out.get("world_objects", [])
            scan_suggestions = out.get("scan_suggestions", [])

            # Persist stable objects in scene_context
            session.scene_context.world_objects = world_objects
            # For legacy/debug: keep raw 3D dets in all_detected_objects
            session.scene_context.all_detected_objects.extend(det3d)

        # Save a CameraFrame in history
        frame = CameraFrame(
            timestamp=request.timestamp or time.time(),
            image_data=request.rgb_base64,
            camera_position=[],
            ar_points=[],
            quality_metrics={
                "geometry": geom_stats,
                "mesh": mesh_info,
            },
            detected_objects=det3d,
        )
        session.add_frame(frame)
        session_manager.auto_save_session(request.session_id)

        return {
            "status": "processed",
            "session_id": request.session_id,
            "frame_id": request.frame_id,
            "current_quality": {
                "coverage": geom_stats.get("coverage", None),
                "unknown_ratio": geom_stats.get("unknown_ratio", None),
            },
            "det2d": det2d,
            "det3d": det3d,
            "world_objects": world_objects,
            "geometry_stats": geom_stats,
            "mesh_info": mesh_info,
            "scan_suggestions": scan_suggestions,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"/session/frame error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/lock_world")
async def lock_world(request: LockWorldRequest):
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")

    mesh_version = session.lock_world()
    session.status = "LOCKED_WORLD"
    session_manager.auto_save_session(request.session_id)

    return {
        "status": "LOCKED_WORLD",
        "session_id": request.session_id,
        "mesh_version": mesh_version,
        "planner_can_run": True,
    }

@app.post("/session/stream")
async def stream_frame(request: StreamFrameRequest):
    """
    Legacy streaming endpoint.

    - If FramePacket fields are present (intrinsics + pose + size), this endpoint proxies to /session/frame.
    - Otherwise it only ingests point_cloud into VoxelWorld (no vision, no 2D->3D).
    """
    try:
        # Fast path: proxy to /session/frame if we have honest geometry inputs.
        if (
            request.width is not None
            and request.height is not None
            and request.fx is not None
            and request.fy is not None
            and request.cx_px is not None
            and request.cy_px is not None
            and request.pose_world_from_camera is not None
            and len(request.pose_world_from_camera) >= 7
        ):
            frame_req = FramePacketRequest(
                session_id=request.session_id,
                frame_id=request.frame_id or f"stream-{int((request.timestamp or time.time()) * 1000)}",
                timestamp=request.timestamp,
                rgb_base64=request.frame_base64,
                width=int(request.width),
                height=int(request.height),
                fx=float(request.fx),
                fy=float(request.fy),
                cx_px=float(request.cx_px),
                cy_px=float(request.cy_px),
                pose_world_from_camera=list(request.pose_world_from_camera),
                depth_base64=request.depth_base64,
                depth_scale=float(request.depth_scale or 1000.0),
                confidence_base64=request.confidence_base64,
                point_cloud=request.point_cloud or [],
                enable_vision=bool(request.enable_vision),
            )
            out = await session_frame(frame_req)
            # Mark as legacy wrapper response
            if isinstance(out, dict):
                out["legacy_stream"] = True
                out["legacy_mode"] = "framepacket_proxy"
            return out

        # Legacy behavior: point_cloud -> VoxelWorld only.
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Сессия не найдена")

        frame = CameraFrame(
            timestamp=request.timestamp or time.time(),
            image_data=request.frame_base64,
            camera_position=request.camera_position or {},
            ar_points=[p.dict() for p in (request.ar_points or [])],
            quality_metrics={
                "incoming_point_cloud_points": len(request.point_cloud or []),
                "legacy_stream": True,
                "vision": "disabled_no_intrinsics_pose",
            },
            detected_objects=[],
        )

        if request.point_cloud and BRAIN_V3_AVAILABLE:
            voxel_world = session.scene_context.ensure_voxel_world()
            if voxel_world is not None:
                added = voxel_world.add_point_cloud(request.point_cloud)
                frame.quality_metrics["voxels_added"] = added
                frame.quality_metrics["total_voxels"] = len(getattr(voxel_world, "occupied", []) or [])

        session.add_frame(frame)
        session_manager.auto_save_session(request.session_id)

        return {
            "status": "processed",
            "session_id": request.session_id,
            "detected_objects": [],
            "context_summary": session.scene_context.get_summary(),
            "legacy_stream": True,
            "legacy_mode": "pointcloud_only",
            "message": "Legacy /session/stream: используйте /session/frame для 2D->3D и unknown-space.",
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate")
async def generate_variants(request: GenerateRequest):
    """
    Генерация вариантов строительных лесов.
    
    КРИТИЧЕСКИ ВАЖНО:
    - Все размеры приводятся к стандартам Layher
    - Если optimize_structure=True → запускается Closed Loop оптимизация
    - Варианты проверяются на коллизии
    - Генерируется BOM для каждого варианта
    """
    try:
        # Получаем сессию
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Сессия не найдена")

        # ── НОВОЕ: AutoScaffolder — умная сборка от целевой точки ────────────
        if request.target_point is not None and BRAIN_V3_AVAILABLE:
            voxel_world = session.scene_context.ensure_voxel_world()

            # Заполняем воксели из YOLO-детекций накопленных в сессии
            # (вспомогательно, если point_cloud не передавался)
            all_dets = session.scene_context.all_detected_objects
            if all_dets and voxel_world.total_voxels == 0:
                voxel_world.ingest_yolo_detections(all_dets)

            from modules.auto_scaffolder import AutoScaffolder
            scaffolder = AutoScaffolder(
                voxel_world=voxel_world,
                ledger_len=request.target_dimensions.get('ledger_len', 1.09),
                standard_h=request.target_dimensions.get('standard_h', 2.07),
                world_objects=getattr(session.scene_context, 'world_objects', None),
            )
            target_dict = {
                "x": request.target_point.x,
                "y": request.target_point.y,
                "z": request.target_point.z,
            }
            floor_z = request.target_dimensions.get('floor_z', 0.0)
            variant = scaffolder.build_to_target(
                target=target_dict,
                floor_z=floor_z,
            )

            # Физический анализ
            analysis = physics_engine.calculate_load_map(
                variant['nodes'], variant['beams']
            )
            variant['physics_analysis'] = {
                "status": analysis.status,
                "max_load_ratio": analysis.max_load_ratio,
                "critical_beams": analysis.critical_beams,
            }

            # Загружаем в структурный граф сессии
            if hasattr(session, 'ensure_structural_graph'):
                graph = session.ensure_structural_graph()
                graph.load_from_variant(variant)

            session.add_variant(variant)

            blocked = sum(1 for b in variant['beams'] if b.get('blocked'))
            return {
                "status": "success",
                "mode": "auto_scaffolder",
                "variants": [variant],
                "count": 1,
                "blocked_beams": blocked,
                "voxels_used": voxel_world.total_voxels,
                "message": (
                    f"AutoScaffolder: башня {variant.get('floors','?')} ярусов. "
                    f"Препятствий в VoxelWorld: {voxel_world.total_voxels}. "
                    f"Обойдено балок: {blocked}."
                )
            }
        # ────────────────────────────────────────────────────────────────────
        # СТАРЫЙ ПУТЬ: target_point не задан → классический генератор
        # Обратная совместимость сохранена.
        # ────────────────────────────────────────────────────────────────────
        
        # Приводим размеры к стандартам
        target_w = snap_to_grid(
            request.target_dimensions.get('width', 4.0), "ledger"
        )
        target_h = snap_to_grid(
            request.target_dimensions.get('height', 3.0), "standard"
        )
        target_d = snap_to_grid(
            request.target_dimensions.get('depth', 2.0), "ledger"
        )
        
        # Собираем точки
        user_points = [p.dict() for p in request.user_points]
        ai_points = session.scene_context.all_ar_points if request.use_ai_detection else []

        all_anchors = list(user_points or []) + list(ai_points or [])
        planner_mode = (getattr(request, "planner_mode", None) or "beam").lower()

        if request.optimize_structure and planner_mode in {"beam", "optimizer", "constraint"}:
            from modules.constraints import ConstraintConfig
            from modules.scaffold_optimizer import ScaffoldOptimizer

            cfg = ConstraintConfig(
                clearance_min=float(request.target_dimensions.get("clearance_min", 0.15)),
                clearance_tentative=float(request.target_dimensions.get("clearance_tentative", 0.30)),
                clearance_needs_scan=float(request.target_dimensions.get("clearance_needs_scan", 0.50)),
                unknown_policy=str(getattr(request, "unknown_policy", "forbid")),
                unknown_buffer=float(request.target_dimensions.get("unknown_buffer", 0.50)),
            )
            optimizer = ScaffoldOptimizer(
                generator=scaffold_generator,
                voxel_world=session.scene_context.voxel_world,
                obstacles=session.scene_context.obstacles,
                config=cfg,
            )
            variants, solve_meta = optimizer.solve(
                bounds={"w": target_w, "h": target_h, "d": target_d},
                anchors=all_anchors,
                max_variants=int(getattr(request, "max_variants", 3) or 3),
                unknown_policy=getattr(request, "unknown_policy", None),
            )

            if not variants:
                return {
                    "status": "insufficient_data",
                    "mode": "constraint_optimizer",
                    "variants": [],
                    "count": 0,
                    "warnings": list(getattr(solve_meta, "warnings", [])),
                    "scan_hints": list(getattr(solve_meta, "scan_hints", [])),
                    "message": "Недостаточно данных: UNKNOWN зоны. Досканьте указанные места или поставьте unknown_policy=buffer.",
                }
        else:
            solve_meta = None
            # Генерируем варианты
            variants = scaffold_generator.generate_smart_options(
                user_points=user_points,
                ai_points=ai_points,
                bounds={"w": target_w, "h": target_h, "d": target_d},
                obstacles=session.scene_context.obstacles,
                voxel_world=session.scene_context.voxel_world,
            )
        
        # Оптимизация каждого варианта (если включено)
        optimized_variants = []
        
        for variant in variants:
            # Быстрая проверка безопасности
            is_safe = quick_safety_check(variant['nodes'], variant['beams'])
            
            if not is_safe:
                variant['warning'] = "Конструкция может быть неустойчивой"
            
            # Closed Loop оптимизация (если включена)
            if request.optimize_structure:
                optimization_result = physics_engine.optimize_structure_closed_loop(
                    variant['nodes'],
                    variant['beams'],
                    target_safety=0.85
                )
                
                # Обновляем вариант оптимизированными данными
                variant['nodes'] = optimization_result['nodes']
                variant['beams'] = optimization_result['beams']
                variant['optimization'] = {
                    "iterations": optimization_result['iterations'],
                    "added_diagonals": optimization_result['added_diagonals'],
                    "optimized": optimization_result['optimized'],
                    "final_load_ratio": optimization_result['final_analysis'].max_load_ratio
                }
            
            # Физический анализ
            analysis = physics_engine.calculate_load_map(
                variant['nodes'],
                variant['beams']
            )
            
            variant['physics_analysis'] = {
                "status": analysis.status,
                "max_load_ratio": analysis.max_load_ratio,
                "critical_beams": analysis.critical_beams,
                "beam_loads": analysis.beam_loads[:10]  # Первые 10 для экономии трафика
            }
            
            # Валидация размеров
            errors = validate_dimensions(variant['nodes'], variant['beams'])
            variant['validation_errors'] = errors
            
            optimized_variants.append(variant)
        
        # Сохраняем варианты в сессии
        for variant in optimized_variants:
            session.add_variant(variant)
        
        return {
            "status": "success",
            "mode": "constraint_optimizer" if (request.optimize_structure and (getattr(request, "planner_mode", "beam") or "beam").lower() in {"beam", "optimizer", "constraint"}) else "legacy_generator",
            "variants": optimized_variants,
            "count": len(optimized_variants),
            "warnings": list(getattr(solve_meta, "warnings", [])) if solve_meta is not None else [],
            "scan_hints": list(getattr(solve_meta, "scan_hints", [])) if solve_meta is not None else [],
            "message": "Варианты сгенерированы и оптимизированы",
        }
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze/physics")
async def analyze_physics(request: AnalyzeRequest):
    """
    Физический анализ конструкции.
    
    Если optimize_if_critical=True и нагрузка > 90%,
    ИИ автоматически пересобирает конструкцию.
    """
    try:
        # Базовый анализ
        analysis = physics_engine.calculate_load_map(
            request.nodes,
            request.beams,
            fixed_node_ids=set(request.fixed_node_ids or [])
        )
        
        result = {
            "status": analysis.status,
            "max_load_ratio": analysis.max_load_ratio,
            "safe": analysis.is_safe(),
            "beam_loads": analysis.beam_loads,
            "critical_beams": analysis.critical_beams,
            "recommendations": analysis.recommended_reinforcements
        }
        
        # Автоматическая оптимизация если критично
        if request.optimize_if_critical and analysis.needs_optimization():
            optimization = physics_engine.optimize_structure_closed_loop(
                request.nodes,
                request.beams,
                fixed_node_ids=set(request.fixed_node_ids or [])
            )
            
            result['auto_optimization'] = {
                "performed": True,
                "iterations": optimization['iterations'],
                "added_diagonals": optimization['added_diagonals'],
                "optimized_nodes": optimization['nodes'],
                "optimized_beams": optimization['beams'],
                "final_load_ratio": optimization['final_analysis'].max_load_ratio,
                "success": optimization['optimized']
            }
            
            result['message'] = (
                f"⚠️ Нагрузка была критической ({analysis.max_load_ratio*100:.0f}%). "
                f"ИИ автоматически добавил {optimization['added_diagonals']} диагоналей. "
                f"Новая нагрузка: {optimization['final_analysis'].max_load_ratio*100:.0f}%"
            )
        
        return result
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/export/bom")
async def export_bom(request: ExportBOMRequest):
    """
    Экспорт Bill of Materials (спецификации) для варианта.
    
    Возвращает CSV файл, по которому можно реально заказать компоненты.
    """
    try:
        session = session_manager.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Сессия не найдена")
        
        if request.variant_index >= len(session.generated_variants):
            raise HTTPException(status_code=400, detail="Неверный индекс варианта")
        
        variant = session.generated_variants[request.variant_index]

        # Генерируем BOM из full_structure (если есть), иначе fallback на beams
        source_elements = variant.get('full_structure') or variant.get('elements')
        if not source_elements:
            source_elements = variant.get('beams', [])

        bom = _build_layher_bom_from_elements(source_elements)
        
        # Генерируем CSV
        csv_content = bom.export_csv()
        
        return {
            "status": "success",
            "csv": csv_content,
            "summary": {
                "total_components": len(bom.components),
                "total_items": sum(bom.components.values()),
                "total_weight_kg": bom.get_total_weight(),
                "estimated_cost_usd": bom.get_total_cost()
            },
            "message": "Спецификация готова для заказа на складе Layher"
        }
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/session/{session_id}/context")
async def get_session_context(session_id: str):
    """Получить контекст сессии (для отладки)"""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return session.get_context_summary()


@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Удалить сессию"""
    success = session_manager.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Сессия не найдена")
    
    return {
        "status": "deleted",
        "session_id": session_id
    }


@app.get("/standards/info")
async def get_standards_info():
    """
    Информация о стандартах Layher.
    
    Android может использовать это для валидации на клиенте.
    """
    return {
        "ledger_lengths": LayherStandards.LEDGER_LENGTHS,
        "standard_heights": LayherStandards.STANDARD_HEIGHTS,
        "diagonal_lengths": LayherStandards.DIAGONAL_LENGTHS,
        "max_loads": {
            "ledgers": LayherStandards.MAX_LEDGER_LOAD,
            "standard": LayherStandards.MAX_STANDARD_LOAD,
            "diagonal": LayherStandards.MAX_DIAGONAL_TENSION
        },
        "safety_thresholds": {
            "critical": LayherStandards.CRITICAL_LOAD_THRESHOLD,
            "warning": LayherStandards.WARNING_LOAD_THRESHOLD
        }
    }


@app.post("/session/depth_stream")
async def ingest_depth_stream(request: DepthStreamRequest):
    if not BRAIN_V3_AVAILABLE:
        raise HTTPException(503, "VoxelWorld модуль не установлен (Brain v3.0)")

    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    try:
        depth_bytes = base64.b64decode(request.depth_base64)
    except Exception as exc:
        raise HTTPException(400, "Ошибка декодирования depth_base64") from exc

    conf_bytes = None
    if request.confidence_base64:
        try:
            conf_bytes = base64.b64decode(request.confidence_base64)
        except Exception as exc:
            raise HTTPException(400, "Ошибка декодирования confidence_base64") from exc

    voxel_world = session.scene_context.ensure_voxel_world()
    normalized_pose = _normalize_camera_pose(request.camera_pose)

    stats = voxel_world.ingest_depth_map(
        depth_bytes=depth_bytes,
        width=request.width,
        height=request.height,
        fx=request.fx,
        fy=request.fy,
        cx_px=request.cx_px,
        cy_px=request.cy_px,
        camera_pose=normalized_pose,
        depth_scale=request.depth_scale,
        confidence_bytes=conf_bytes,
        confidence_threshold=request.confidence_threshold,
        pixel_step=request.pixel_step,
    )

    tsdf = session.scene_context.ensure_tsdf_integrator()
    tsdf_integrated = False
    if tsdf is not None and getattr(tsdf, "available", False):
        import numpy as _np

        d = _np.frombuffer(depth_bytes, dtype=_np.uint16).reshape(request.height, request.width)
        depth_m = d.astype(_np.float32) / float(request.depth_scale)
        pose7 = (
            float(normalized_pose[0]),
            float(normalized_pose[1]),
            float(normalized_pose[2]),
            float(normalized_pose[3]),
            float(normalized_pose[4]),
            float(normalized_pose[5]),
            float(normalized_pose[6]),
        )
        tsdf_integrated = bool(
            tsdf.integrate_depth(
                depth_m=depth_m,
                fx=request.fx,
                fy=request.fy,
                cx=request.cx_px,
                cy=request.cy_px,
                pose_world_from_camera_7=pose7,
            )
        )

    quality = voxel_world.get_quality_metrics()

    return {
        "status": "world_updated",
        "camera_pose": normalized_pose,
        "depth_payload_bytes": len(depth_bytes),
        "depth_scale": request.depth_scale,
        "depth_stats": stats,
        "quality": quality,
        "total_occupied_voxels": voxel_world.total_voxels,
        "total_known_voxels": voxel_world.total_known_voxels,
        "tsdf_integrated": tsdf_integrated,
        "message": "Depth интегрирован: FREE/OCCUPIED обновлены, UNKNOWN уменьшен (консервативный режим).",
    }


def _get_session_voxels_payload(session_id: str) -> Dict[str, Any]:
    """Единый payload вокселей для мобильной визуализации (Eye of AI)."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    scene_context = session.scene_context
    voxel_world = scene_context.ensure_voxel_world() if BRAIN_V3_AVAILABLE else None

    if voxel_world is None:
        return {
            "status": "OK",
            "voxels": [],
            "bounds": {"min": [-5.0, -1.0, -5.0], "max": [5.0, 4.0, 5.0]},
            "resolution": 0.25,
            "total_count": 0,
            "message": "VoxelWorld недоступен",
        }

    if scene_context.point_cloud:
        pc_points = []
        for point in scene_context.point_cloud:
            if isinstance(point, dict):
                pc_points.append([
                    float(point.get("x", 0.0)),
                    float(point.get("y", 0.0)),
                    float(point.get("z", 0.0)),
                ])
            elif isinstance(point, (list, tuple)) and len(point) >= 3:
                pc_points.append([float(point[0]), float(point[1]), float(point[2])])
        if pc_points:
            voxel_world.add_point_cloud(pc_points)

    voxels_data: List[Dict[str, Any]] = []

    type_to_name = {
        voxel_world.FLOOR: "ground",
        voxel_world.OCCUPIED: "obstacle",
        voxel_world.PIPE: "obstacle",
        voxel_world.WALL: "obstacle",
    }
    type_to_color = {
        "obstacle": "red",
        "structure": "blue",
        "ground": "gray",
        "available": "green",
        "forbidden": "yellow",
    }
    type_to_alpha = {
        "obstacle": 0.7,
        "structure": 0.5,
        "ground": 0.3,
        "available": 0.3,
        "forbidden": 0.5,
    }

    for voxel_key in voxel_world.occupied:
        vtype = voxel_world._types.get(voxel_key, voxel_world.OCCUPIED)
        type_name = type_to_name.get(vtype, "available")
        x, y, z = (
            voxel_key[0] * voxel_world.resolution,
            voxel_key[1] * voxel_world.resolution,
            voxel_key[2] * voxel_world.resolution,
        )
        voxels_data.append(
            {
                "position": [x, y, z],
                "type": type_name,
                "color": type_to_color[type_name],
                "alpha": type_to_alpha[type_name],
            }
        )

    for element in session.current_structure:
        start = element.get("start", {}) or {}
        end = element.get("end", {}) or {}
        sx, sy, sz = float(start.get("x", 0.0)), float(start.get("y", 0.0)), float(start.get("z", 0.0))
        ex, ey, ez = float(end.get("x", 0.0)), float(end.get("y", 0.0)), float(end.get("z", 0.0))
        voxels_data.append(
            {
                "position": [(sx + ex) / 2.0, (sy + ey) / 2.0, (sz + ez) / 2.0],
                "type": "structure",
                "color": type_to_color["structure"],
                "alpha": type_to_alpha["structure"],
            }
        )

    metadata = getattr(session, "metadata", {}) or {}
    forbidden_zones = metadata.get("forbidden_zones", []) if isinstance(metadata, dict) else []
    for zone in forbidden_zones:
        center = zone.get("center", [0.0, 0.0, 0.0])
        radius = float(zone.get("radius", 1.0))
        if not (isinstance(center, list) and len(center) >= 3):
            center = [0.0, 0.0, 0.0]

        voxels_data.append(
            {
                "position": [float(center[0]), float(center[1]), float(center[2])],
                "type": "forbidden",
                "color": type_to_color["forbidden"],
                "alpha": type_to_alpha["forbidden"],
                "radius": radius,
            }
        )

    points_for_bounds = [v["position"] for v in voxels_data if isinstance(v.get("position"), list) and len(v["position"]) >= 3]
    if points_for_bounds:
        xs = [p[0] for p in points_for_bounds]
        ys = [p[1] for p in points_for_bounds]
        zs = [p[2] for p in points_for_bounds]
        bounds = {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        }
    else:
        bounds = {"min": [-5.0, -1.0, -5.0], "max": [5.0, 4.0, 5.0]}

    return {
        "status": "OK",
        "voxels": voxels_data,
        "bounds": bounds,
        "resolution": voxel_world.resolution,
        "total_count": len(voxels_data),
    }


@app.get("/session/{session_id}/voxel_map")
async def get_voxel_map(session_id: str):
    return _get_session_voxels_payload(session_id)


@app.get("/session/voxels/{session_id}")
async def get_voxel_visualization(session_id: str):
    """Вернуть визуализацию вокселей для отладки и режима Eye of AI."""
    return _get_session_voxels_payload(session_id)


@app.post("/generate/auto")
async def generate_auto_scaffold(request: AutoScaffoldRequest):
    if not BRAIN_V3_AVAILABLE:
        raise HTTPException(503, "AutoScaffolder модуль не установлен (Brain v3.0)")

    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    voxel_world = session.scene_context.ensure_voxel_world()

    all_detections = session.scene_context.all_detected_objects
    if all_detections:
        voxel_world.ingest_yolo_detections(all_detections)

    target_dict = {"x": request.target.x, "y": request.target.y, "z": request.target.z}

    scaffolder = AutoScaffolder(
        voxel_world=voxel_world,
        ledger_len=request.ledger_len,
        standard_h=request.standard_h,
    )

    try:
        variant = scaffolder.build_to_target(
            target=target_dict,
            clearance_box=request.clearance_box,
            floor_z=request.floor_z,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    analysis = physics_engine.calculate_load_map(variant["nodes"], variant["beams"])
    variant["physics_analysis"] = {
        "status": analysis.status,
        "max_load_ratio": analysis.max_load_ratio,
        "critical_beams": analysis.critical_beams,
    }

    graph = session.ensure_structural_graph()
    graph.load_from_variant(variant)
    session.add_variant(variant)

    blocked_count = sum(1 for b in variant["beams"] if b.get("blocked"))

    return {
        "status": "success",
        "variant": variant,
        "graph_summary": graph.get_summary(),
        "blocked_beams": blocked_count,
        "message": (
            f"Башня {variant['floors']} ярусов построена. "
            f"Препятствий обойдено: {blocked_count}. "
            f"Статус физики: {analysis.status}"
        ),
    }


@app.post("/structure/modify")
async def modify_structure(request: StructureModifyRequest):
    session = session_manager.get_session(request.session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    if not BRAIN_V3_AVAILABLE:
        raise HTTPException(503, "StructuralGraph модуль не установлен")

    graph = session.ensure_structural_graph()

    if not graph.get_beams() and session.generated_variants:
        graph.load_from_variant(session.generated_variants[-1])

    t_start = time.time()

    if request.action == "REMOVE":
        if not request.element_id:
            raise HTTPException(400, "element_id обязателен для REMOVE")
        result = graph.remove_element(request.element_id)
    elif request.action == "ADD":
        if not request.element_data:
            raise HTTPException(400, "element_data обязателен для ADD")
        result = graph.add_beam(request.element_data)
    else:
        raise HTTPException(400, f"Неизвестный action: {request.action}")

    elapsed_ms = (time.time() - t_start) * 1000

    full_analysis = None
    if not result.get("is_stable") and session.generated_variants:
        try:
            full_analysis = physics_engine.calculate_load_map(graph.get_nodes(), graph.get_beams())
        except Exception:
            pass

    return {
        "status": "UPDATED",
        "action": request.action,
        "element_id": request.element_id,
        "heatmap": result.get("heatmap", []),
        "is_stable": result.get("is_stable", True),
        "affected": result.get("affected", []),
        "elapsed_ms": round(elapsed_ms, 1),
        "full_analysis": {
            "status": full_analysis.status,
            "max_load_ratio": full_analysis.max_load_ratio,
        }
        if full_analysis
        else None,
        "animation_hint": "COLLAPSE" if not result.get("is_stable") else "UPDATE",
        "message": (
            "⚠️ КОНСТРУКЦИЯ НЕСТАБИЛЬНА — добавьте диагонали!"
            if not result.get("is_stable")
            else f"Обновлено за {elapsed_ms:.0f} мс"
        ),
    }


@app.post("/session/model/{session_id}")
async def finalize_model(session_id: str):
    """
    Финализация модели с полным циклом: A* → PostProcessor → Physics.
    """
    if not BRAIN_V3_AVAILABLE:
        raise HTTPException(503, "Brain v3.2 модули недоступны")

    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(404, "Сессия не найдена")

    try:
        from modules.session import DesignSession

        if isinstance(session, DesignSession):
            user_anchors = session.user_anchors
        else:
            user_anchors = session.scene_context.anchor_points or session.scene_context.all_ar_points
    except Exception:
        user_anchors = []

    if not user_anchors:
        return {
            "status": "ERROR",
            "message": "No anchor points defined. User must place markers in AR first.",
        }

    print(f"🏗️  Industrial AI Modeling for {session_id}... ({len(user_anchors)} anchors)")

    start_anchor = user_anchors[0]
    end_anchor = user_anchors[-1]

    start_node = {
        "x": start_anchor.get("x", 0),
        "y": start_anchor.get("y", 0),
        "z": start_anchor.get("z", 0),
    }
    target_node = {
        "x": end_anchor.get("x", 0),
        "y": end_anchor.get("y", 0),
        "z": end_anchor.get("z", 0) + 2.0,
    }

    raw_points = [[p.get("x", 0), p.get("y", 0), p.get("z", 0)] for p in session.scene_context.point_cloud]
    target_dims = {
        "height": round(max(0.0, target_node["z"] - start_node["z"]), 3),
        "span_x": round(abs(target_node["x"] - start_node["x"]), 3),
        "span_y": round(abs(target_node["y"] - start_node["y"]), 3),
    }

    try:
        voxel_world = session.scene_context.ensure_voxel_world()
        pathfinder = ScaffoldPathfinder(voxel_world)
        path_segments = pathfinder.find_path(start_node, target_node)

        if not path_segments:
            return {
                "status": "FAILURE",
                "message": "Path blocked or impossible. Check VoxelWorld obstacles.",
                "voxels_in_world": voxel_world.total_voxels,
            }

        skeleton = []
        for i, seg in enumerate(path_segments):
            if isinstance(seg, dict) and "start" in seg and "end" in seg:
                skeleton.append(
                    {
                        "id": f"sk_{i}",
                        "type": seg.get("type", "ledger"),
                        "start": seg["start"],
                        "end": seg["end"],
                        "length": seg.get("length", 2.0),
                        "weight": 10.0,
                    }
                )

        full_structure = post_processor.process(skeleton)

        print(
            f"  PostProcessor: {len(skeleton)} → {len(full_structure)} elements "
            f"(added {len(full_structure) - len(skeleton)} bracing/decks)"
        )

        reinforcement_iterations = 0
        max_reinforcement_iterations = 5
        physics_data = []
        physics_status = "COLLAPSE"

        while reinforcement_iterations <= max_reinforcement_iterations:
            phys_nodes = []
            phys_beams = []
            seen_nodes = set()

            for el in full_structure:
                for p in [el["start"], el["end"]]:
                    k = f"{p[0]:.2f}_{p[1]:.2f}_{p[2]:.2f}"
                    if k not in seen_nodes:
                        phys_nodes.append({"id": k, "x": p[0], "y": p[1], "z": p[2], "fixed": abs(p[2]) < 0.1})
                        seen_nodes.add(k)

                s = el["start"]
                e = el["end"]
                phys_beams.append(
                    {
                        "id": el["id"],
                        "type": el["type"],
                        "start": f"{s[0]:.2f}_{s[1]:.2f}_{s[2]:.2f}",
                        "end": f"{e[0]:.2f}_{e[1]:.2f}_{e[2]:.2f}",
                        "length": el.get("length", 0),
                    }
                )

            physics_res = physics_engine.calculate_load_map(phys_nodes, phys_beams)

            if isinstance(physics_res, dict):
                physics_status = physics_res.get("status", "COLLAPSE")
                physics_data = physics_res.get("data", [])
            else:
                physics_status = getattr(physics_res, "status", "COLLAPSE")
                physics_data = getattr(physics_res, "beam_loads", [])

            if physics_status != "COLLAPSE":
                break
            if reinforcement_iterations >= max_reinforcement_iterations:
                break

            before_len = len(full_structure)
            full_structure = post_processor.process(full_structure)
            added = len(full_structure) - before_len
            reinforcement_iterations += 1
            print(f"  Reinforcement loop #{reinforcement_iterations}: status=COLLAPSE, added {max(0, added)} elements")
            if added <= 0:
                break

        safety_score = 0
        if physics_status == "OK":
            loads = [r.get("load_ratio", 0) for r in physics_data]
            if loads:
                max_load = max(loads)
                safety_score = int((1.0 - min(max_load, 1.0)) * 100)
                by_id = {item.get("id"): item for item in physics_data}
                for el in full_structure:
                    phys_item = by_id.get(el.get("id"))
                    if phys_item:
                        el["load_ratio"] = phys_item.get("load_ratio", 0.0)
                        el["stress_color"] = phys_item.get("color", "green")
            else:
                safety_score = 100
        else:
            print("⚠️  Physics calculation FAILED (Structure unstable)")

        layher_bom = _build_layher_bom_from_elements(full_structure)

        final_options = [{
            "id": 1,
            "name": "AI Engineered (Layher Allround)",
            "elements": [],
            "full_structure": full_structure,
            "safety_score": safety_score,
            "total_weight": sum(e.get("weight", 0) for e in full_structure),
            "physics_status": physics_status,
            "bom": {
                "csv": layher_bom.export_csv(),
                "components": layher_bom.components,
                "total_weight_kg": layher_bom.get_total_weight(),
                "estimated_cost_usd": layher_bom.get_total_cost(),
            },
        }]

        for el in full_structure:
            final_options[0]["elements"].append(
                {
                    "id": el.get("id", "gen"),
                    "type": el["type"],
                    "start": {"x": el["start"][0], "y": el["start"][1], "z": el["start"][2]},
                    "end": {"x": el["end"][0], "y": el["end"][1], "z": el["end"][2]},
                    "length": el.get("length", 0),
                    "stress_color": el.get("stress_color", "green"),
                    "load_ratio": el.get("load_ratio", 0.0),
                }
            )

        session.save_structure(final_options[0]["elements"])
        session_manager.auto_save_session(session_id)

        mesh = mesh_builder.build_from_elements(final_options[0]["elements"])
        final_options[0]["mesh"] = {
            "vertices": mesh.vertices.tolist()[:1000] if hasattr(mesh, "vertices") else [],
            "faces": mesh.faces.tolist()[:1000] if hasattr(mesh, "faces") else [],
            "vertex_colors": (
                mesh.visual.vertex_colors.tolist()[:1000]
                if hasattr(mesh, "visual") and hasattr(mesh.visual, "vertex_colors")
                else []
            ),
            "statistics": mesh_builder.get_statistics(),
        }
        final_options[0]["inspection"] = scaffold_inspector.inspect(final_options[0]["elements"], physics_data)

        return {
            "status": "SUCCESS",
            "options": final_options,
            "statistics": {
                "skeleton_elements": len(skeleton),
                "total_elements": len(full_structure),
                "added_diagonals": sum(1 for e in full_structure if e["type"] == "diagonal"),
                "added_decks": sum(1 for e in full_structure if e["type"] == "deck"),
                "reinforcement_iterations": reinforcement_iterations,
                "voxels_used": voxel_world.total_voxels,
            },
        }
    except Exception as e:
        debug_dumper.dump_generation_error(
            session_id=session_id,
            point_cloud=raw_points,
            user_anchors=user_anchors,
            target_dimensions=target_dims,
            error=e,
            traceback_str=traceback.format_exc(),
        )
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/session/update/{session_id}")
async def update_structure_realtime(session_id: str, action: SessionUpdateAction):
    start_time = time.time()
    if not validate_session_exists(session_id, session_manager):
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_manager.get_session(session_id)
    if not session.current_structure:
        raise HTTPException(status_code=400, detail="No structure to update")

    if action.action == "REMOVE":
        if not session.remove_element(action.element_id):
            raise HTTPException(status_code=404, detail="Element not found")
    else:
        session.add_element(action.element_data.model_dump())

    phys_nodes = []
    phys_beams = []
    seen_nodes = set()
    for el in session.current_structure:
        for point in [el.get("start"), el.get("end")]:
            if not point:
                continue
            node_key = f"{point.get('x', 0):.2f}_{point.get('y', 0):.2f}_{point.get('z', 0):.2f}"
            if node_key not in seen_nodes:
                phys_nodes.append({
                    "id": node_key,
                    "x": point.get("x", 0),
                    "y": point.get("y", 0),
                    "z": point.get("z", 0),
                    "fixed": abs(point.get("z", 0)) < 0.1,
                })
                seen_nodes.add(node_key)
        start_point = el.get("start", {})
        end_point = el.get("end", {})
        phys_beams.append({
            "id": el.get("id"),
            "type": el.get("type"),
            "start": f"{start_point.get('x', 0):.2f}_{start_point.get('y', 0):.2f}_{start_point.get('z', 0):.2f}",
            "end": f"{end_point.get('x', 0):.2f}_{end_point.get('y', 0):.2f}_{end_point.get('z', 0):.2f}",
            "length": el.get("length", 0),
        })

    collapsed_nodes = []
    collapsed_elements = []
    graph = session.ensure_structural_graph()
    if graph is not None:
        graph.load_from_variant({"nodes": phys_nodes, "beams": phys_beams})
        detached = graph.find_detached_substructures()
        collapsed_nodes = detached.get("nodes", [])
        collapsed_elements = detached.get("beams", [])

        if collapsed_elements:
            collapsed_set = set(collapsed_elements)
            session.current_structure = [
                element for element in session.current_structure if element.get("id") not in collapsed_set
            ]
            phys_beams = [beam for beam in phys_beams if beam.get("id") not in collapsed_set]
            nodes_in_use = {beam["start"] for beam in phys_beams} | {beam["end"] for beam in phys_beams}
            phys_nodes = [node for node in phys_nodes if node.get("id") in nodes_in_use]

    validation = validate_structure_stability(session.current_structure)
    if not validation["is_valid"]:
        logger.warning("Structure validation failed: %s", validation["errors"])

    physics_res = physics_engine.calculate_load_map(phys_nodes, phys_beams)
    physics_status = physics_res.get("status", "COLLAPSE")
    physics_data = physics_res.get("data", [])

    by_id = {item.get("id"): item for item in physics_data}
    affected = []
    for element in session.current_structure:
        phys_item = by_id.get(element.get("id"))
        if phys_item:
            old_ratio = element.get("load_ratio", 0)
            new_ratio = phys_item.get("load_ratio", 0)
            element["load_ratio"] = new_ratio
            element["stress_color"] = phys_item.get("color", "green")
            if abs(new_ratio - old_ratio) > 0.1:
                affected.append(element.get("id"))

    if hasattr(physics_engine, "invalidate_cache"):
        physics_engine.invalidate_cache()
    session_manager.auto_save_session(session_id)

    return {
        "status": "UPDATED",
        "is_stable": physics_status != "COLLAPSE",
        "physics_status": physics_status,
        "heatmap": physics_data,
        "affected_elements": affected,
        "collapsed": {
            "nodes": collapsed_nodes,
            "elements": collapsed_elements,
        },
        "validation": validation,
        "processing_time_ms": int((time.time() - start_time) * 1000),
    }


@app.post("/session/preview_remove/{session_id}")
async def preview_remove(session_id: str, element_id: str):
    """Preview structural impact of an element removal without mutating structure."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    graph = session.ensure_structural_graph()
    if graph is None:
        return {"is_critical": False, "would_collapse_count": 0}

    phys_nodes = []
    phys_beams = []
    seen_nodes = set()

    for el in session.current_structure:
        for p in [el.get("start"), el.get("end")]:
            if not p:
                continue
            k = f"{p.get('x', 0):.2f}_{p.get('y', 0):.2f}_{p.get('z', 0):.2f}"
            if k not in seen_nodes:
                phys_nodes.append({
                    "id": k,
                    "x": p.get("x", 0),
                    "y": p.get("y", 0),
                    "z": p.get("z", 0),
                    "fixed": abs(p.get("z", 0)) < 0.1,
                })
                seen_nodes.add(k)

        s = el.get("start", {})
        e = el.get("end", {})
        phys_beams.append({
            "id": el.get("id"),
            "type": el.get("type"),
            "start": f"{s.get('x', 0):.2f}_{s.get('y', 0):.2f}_{s.get('z', 0):.2f}",
            "end": f"{e.get('x', 0):.2f}_{e.get('y', 0):.2f}_{e.get('z', 0):.2f}",
            "length": el.get("length", 0),
        })

    graph.load_from_variant({"nodes": phys_nodes, "beams": phys_beams})
    criticality = graph.check_element_criticality(element_id)

    return {
        "status": "PREVIEW",
        "element_id": element_id,
        "is_critical": criticality["is_critical"],
        "would_collapse": criticality["affected_beams"],
        "collapse_count": criticality["would_collapse_count"],
        "warning": (
            f"⚠️ Удаление этого элемента приведет к обрушению {criticality['would_collapse_count']} элементов!"
            if criticality["is_critical"]
            else "✅ Этот элемент можно безопасно удалить."
        ),
    }


@app.post("/session/beautify/{session_id}")
async def beautify_environment(session_id: str, depth: int = 9):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.scene_context.point_cloud:
        raise HTTPException(status_code=400, detail="No point cloud available")

    raw_points = [[p.get("x", 0), p.get("y", 0), p.get("z", 0)] for p in session.scene_context.point_cloud]
    if point_cloud_processor.last_pcd is None:
        point_cloud_processor.process_raw_points(raw_points)

    result = point_cloud_processor.poisson_reconstruction(depth=depth)
    if not result:
        raise HTTPException(status_code=500, detail="Reconstruction failed")

    return {"status": "SUCCESS", "environment_mesh": result, "statistics": result["statistics"]}


@app.get("/session/export/{session_id}")
async def export_session_bom(session_id: str, format: str = "csv", project_name: str = "Unnamed Project"):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.current_structure and not session.generated_variants:
        raise HTTPException(status_code=400, detail="No structure to export")

    elements = session.current_structure or session.generated_variants[0].get("full_structure", [])
    bom = _build_layher_bom_from_elements(elements)

    if format == "csv":
        csv_data = bom_exporter.export_to_csv(bom, project_name)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=BOM_{session_id}.csv"},
        )
    if format == "xlsx":
        filepath = f"/tmp/BOM_{session_id}.xlsx"
        if not bom_exporter.export_to_excel(bom, filepath, project_name):
            raise HTTPException(status_code=500, detail="Excel export failed")
        return FileResponse(filepath, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=f"BOM_{session_id}.xlsx")
    if format == "pdf":
        filepath = f"/tmp/BOM_{session_id}.pdf"
        if not bom_exporter.export_to_pdf(bom, filepath, project_name):
            raise HTTPException(status_code=500, detail="PDF export failed")
        return FileResponse(filepath, media_type="application/pdf", filename=f"BOM_{session_id}.pdf")

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@app.post("/session/inspect/{session_id}")
async def inspect_quality(session_id: str):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.current_structure and not session.generated_variants:
        raise HTTPException(status_code=400, detail="No structure to inspect")

    elements = session.current_structure or session.generated_variants[0].get("full_structure", [])
    physics_data = None
    if session.generated_variants and "options" in session.generated_variants[0]:
        opts = session.generated_variants[0].get("options", [])
        if opts:
            physics_data = opts[0].get("physics_data")

    return scaffold_inspector.inspect(elements, physics_data)


@app.get("/session/debug_dump/{session_id}")
async def get_debug_dump(session_id: str, include_voxels: bool = False):
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session_json = session_manager.export_session_data(session_id)
    if not session_json:
        raise HTTPException(status_code=500, detail="Failed to export session")

    filepath = debug_dumper.dump_session(
        session_id=session_id,
        session_data=json.loads(session_json),
        reason="manual",
        include_voxels=include_voxels,
    )
    return FileResponse(filepath, media_type="application/json", filename=f"debug_{session_id}.json")


@app.get("/debug/list_dumps")
async def list_debug_dumps(session_id: Optional[str] = None):
    dumps = debug_dumper.list_dumps(session_id)
    return {"total": len(dumps), "dumps": dumps}


@app.get("/metrics")
async def get_metrics():
    """Метрики производительности, запросов и кэша."""
    return {
        "performance": performance_monitor.get_stats(),
        "requests": {
            "recent": request_logger.get_recent_requests(limit=20),
            "errors": request_logger.get_error_requests(limit=10),
        },
        "cache": global_cache.get_stats(),
    }


@app.websocket("/ws/{session_id}")
async def websocket_structure(websocket: WebSocket, session_id: str):
    await websocket.accept()

    session = session_manager.get_session(session_id)
    if not session:
        await websocket.send_json({"type": "ERROR", "message": "Сессия не найдена"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action", "")

            if action == "PING":
                await websocket.send_json({"type": "PONG"})
                continue

            if action in ("REMOVE", "ADD") and BRAIN_V3_AVAILABLE:
                graph = session.ensure_structural_graph()
                if not graph.get_beams() and session.generated_variants:
                    graph.load_from_variant(session.generated_variants[-1])

                if action == "REMOVE":
                    result = graph.remove_element(data.get("element_id", ""))
                else:
                    result = graph.add_beam(data.get("element_data", {}))

                await websocket.send_json(
                    {
                        "type": "HEATMAP",
                        "heatmap": result.get("heatmap", []),
                        "is_stable": result.get("is_stable", True),
                        "affected": result.get("affected", []),
                        "animation": "COLLAPSE" if not result.get("is_stable") else "UPDATE",
                    }
                )
                continue

            await websocket.send_json({"type": "ERROR", "message": f"Неизвестный action: {action}"})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "ERROR", "message": str(exc)})
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Глобальный обработчик ошибок"""
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": str(exc),
            "type": type(exc).__name__
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    """Инициализация при запуске"""
    print("=" * 70)
    print("🚀 AI BRAIN BACKEND STARTING")
    print("=" * 70)
    print(f"✓ Layher Standards: {len(LayherStandards.LEDGER_LENGTHS)} ledger lengths")
    print("✓ Physics Engine: PyNite FEM")
    print("✓ Collision Solver: Trimesh integration")
    print("✓ Session Manager: Ready")
    print(f"{'✓' if BRAIN_V3_AVAILABLE else '✗'} Brain v3.0: VoxelWorld + A* + StructuralGraph")
    if not BRAIN_V3_AVAILABLE:
        print("  ⚠️  Установите: pip install networkx websockets")
    print("=" * 70)


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
