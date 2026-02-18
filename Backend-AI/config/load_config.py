from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ServerCfg(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class StorageCfg(BaseModel):
    sessions_root: str = "sessions"


class WorldCfg(BaseModel):
    voxel_size_m: float = 0.20
    tsdf_trunc_m: float = 0.40


class ExportOverlaysCfg(BaseModel):
    occupancy_npz: bool = True
    occupancy_slice_png: bool = True


class ExportCfg(BaseModel):
    env_mesh_format: str = "obj"
    overlays: ExportOverlaysCfg = Field(default_factory=ExportOverlaysCfg)


class PolicyCfg(BaseModel):
    policy_yaml_path: str | None = None


class AppConfig(BaseModel):
    server: ServerCfg = Field(default_factory=ServerCfg)
    storage: StorageCfg = Field(default_factory=StorageCfg)
    world: WorldCfg = Field(default_factory=WorldCfg)
    export: ExportCfg = Field(default_factory=ExportCfg)
    policy: PolicyCfg = Field(default_factory=PolicyCfg)


def load_app_config(path: Path) -> AppConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config YAML must be a mapping, got {type(raw).__name__}")
    return AppConfig(**raw)


def find_default_config() -> Path | None:
    candidates = [
        Path("config") / "default.yaml",
        Path("Backend-AI") / "config" / "default.yaml",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None
