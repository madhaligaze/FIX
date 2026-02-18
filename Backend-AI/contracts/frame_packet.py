from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Intrinsics(BaseModel):
    fx: float = Field(gt=0)
    fy: float = Field(gt=0)
    cx: float
    cy: float
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class Pose(BaseModel):
    # Canonical pose uses position + quaternion ([x,y,z], [x,y,z,w]) in world frame.
    position: list[float] = Field(min_length=3, max_length=3)
    quaternion: list[float] = Field(min_length=4, max_length=4)


class DepthMeta(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    scale_m_per_unit: float = Field(gt=0)
    encoding: str = "uint16"


class PointCloudMeta(BaseModel):
    format: Literal["npy", "ply", "xyz"]
    frame: Literal["world", "camera"]


class FramePacketMeta(BaseModel):
    session_id: str
    frame_id: str
    timestamp: float
    intrinsics: Intrinsics
    pose: Pose
    depth_meta: DepthMeta | None = None
    pointcloud_meta: PointCloudMeta | None = None

    @model_validator(mode="after")
    def _validate_depth_or_cloud(self) -> "FramePacketMeta":
        if self.depth_meta is None and self.pointcloud_meta is None:
            raise ValueError("Either depth_meta or pointcloud_meta must be provided")
        return self


class AnchorPoint(BaseModel):
    id: str
    position: list[float] = Field(min_length=3, max_length=3)
    kind: Literal["support", "boundary", "forbidden", "target"]
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
