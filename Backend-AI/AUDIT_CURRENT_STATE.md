# AUDIT_CURRENT_STATE (Backend-AI)

Snapshot: 2026-02-18

This document is a quick "what is implemented" index for reviewers and enterprise ops.

## Key endpoints

- POST /session/create
- POST /session/frame
- POST /session/anchors
- GET  /session/{session_id}/status
- POST /session/lock
- GET  /metrics
- GET  /health

## Stage coverage pointers (code map)

A. Data Contracts
- contracts/frame_packet.py
- validation/frame_validation.py
- api/routes_session_v2.py (v2 routes now enforce strict validation + monotonic timestamps)
- contracts/framespec.md (coordinate frames)

B. TSDF / Occupancy
- world/tsdf_volume.py
- world/occupancy.py
- world/world_model.py

C. Tracking Quality
- tracking/pose_quality.py (pose jump detection)
- tracking/icp_refinement.py (ICP registration helper)
- world/world_model.py (ICP-based pose refinement using depth)

D. Readiness + NBV
- scanning/readiness.py
- scanning/next_best_view.py

E. Scene Semantics
- perception/scene_graph.py
- perception/primitive_fit.py
- perception/object_tracker.py

F. Hypotheses
- inference/extend_linear_objects.py

G. ESDF
- world/esdf.py

H. Scaffold Planner
- scaffold/planner.py
- trace/trace.py (decision audit)

I. Android Export
- export/scene_bundle.py
- Android/app/src/main/java/com/example/aibrain/...

J. Enterprise Ops
- observability/metrics.py + observability/metrics_middleware.py + /metrics endpoint
- observability/tracing.py (OpenTelemetry opt-in)
- security/rate_limit.py (per API key / per IP)
- main.py uses FastAPI lifespan for background jobs (retention cleanup)

## Known limitations / TODO

- ICP refinement is conservative by default; tune tracking.* thresholds for your site.
- Access control for /sessions static path should be enforced at the gateway (reverse proxy) in production.
