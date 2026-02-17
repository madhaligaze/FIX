# FramePacket protocol (Android -> Backend)

Endpoint: `POST /session/frame`

Required fields
- `session_id`
- `frame_base64` (jpeg/png bytes, base64)
- `camera_pose` in world coordinates: `[tx, ty, tz, qx, qy, qz, qw]`
- intrinsics: `fx`, `fy`, `cx_px`, `cy_px`

Optional geometry inputs
- `depth_base64` (uint16 depth in mm, row-major)
- `depth_width`, `depth_height`
- `point_cloud`: list of `[x, y, z]` world points from ARCore

What the backend does
1. Integrates geometry into `VoxelWorld`:
   - `depth` => FREE carving + OCCUPIED hits
   - `point_cloud` => OCCUPIED samples
2. Runs 2D detection (if available) and lifts to 3D (depth+intrinsics+pose).
3. Tracks objects across frames (stabilization).
4. Stage 5: checks model vs depth (reprojection).
5. Stage 6: turns scan suggestions into actionable view proposals.

Response fields (high level)
- `detected_objects`
- `context_summary`
- `geometry_stats`:
  - voxel ingest counters
  - `unknown_local_ratio`
  - `reprojection` metrics
- `scan_suggestions` (world points)
- `scan_plan` (clusters + next_best_views)
