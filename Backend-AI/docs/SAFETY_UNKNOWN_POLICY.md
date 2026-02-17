# UNKNOWN space policy

VoxelWorld has 3 logical states for each cell:
- OCCUPIED: confirmed obstacle / solid
- FREE: confirmed empty space (ray-carved)
- UNKNOWN: everything else (not observed yet)

Rules
1. Any planning that can affect safety must treat UNKNOWN as blocked.
2. Any "completion" decision (e.g. locking the world or exporting final scaffold) must be gated by:
   - Stage 5 reprojection passes (`reprojection.ok=true`), and
   - low UNKNOWN density around the relevant area.

Why
Depth and point clouds have occlusions; without this policy, the system can hallucinate safe space.
