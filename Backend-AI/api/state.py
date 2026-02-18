from __future__ import annotations

from dataclasses import dataclass, field

from perception.scene_graph import SceneGraph
from policy.policy_config import PolicyConfig
from session.session_store import SessionStore
from world.world_model import WorldModel


@dataclass
class RuntimeState:
    config: dict
    store: SessionStore
    policy: PolicyConfig

    worlds: dict[str, WorldModel] = field(default_factory=dict)
    scene_graphs: dict[str, SceneGraph] = field(default_factory=dict)

    anchors: dict[str, list[dict]] = field(default_factory=dict)
    traces: dict[str, list[dict]] = field(default_factory=dict)
    last_rev: dict[str, str] = field(default_factory=dict)
    restored_revision_state: dict[str, dict] = field(default_factory=dict)
    perception_unavailable: bool = False

    def get_world(self, session_id: str) -> WorldModel:
        if session_id not in self.worlds:
            self.worlds[session_id] = WorldModel(
                voxel_size=float(self.config.get("world", {}).get("voxel_size", 0.2)),
                tsdf_trunc=float(self.config.get("world", {}).get("tsdf_trunc", 0.4)),
            )
        return self.worlds[session_id]

    def get_scene_graph(self, session_id: str) -> SceneGraph:
        if session_id not in self.scene_graphs:
            self.scene_graphs[session_id] = SceneGraph()
        return self.scene_graphs[session_id]

    def policy_status(self) -> dict:
        return {"policy": self.policy.__dict__, "source": self.config.get("policy_source")}
