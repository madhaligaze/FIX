# Data Retention Policy (Backend-AI)

This repository stores scanning sessions under the directory configured by:

Backend-AI/config/default.yaml -> storage.sessions_root

## What is stored

A session directory contains:
- frames/<frame_id>/
  - meta.json (raw)
  - validated_meta.json (normalized)
  - rgb.jpg
  - depth.u16 (optional)
  - pointcloud.bin (optional)
- anchors/anchors.json
- world/<rev_id>/
  - world_state.json
  - overlays.json
  - trace.json + trace.ndjson
  - env_mesh.obj (optional)
- exports/<rev_id>/scene_bundle.json

These artifacts may contain operationally sensitive information (images of shop floors, device trajectories, etc.).

## Default retention behavior

Retention is enforced by a background cleanup loop started via FastAPI lifespan:

- Enabled: retention.enabled (default true)
- Max session age: retention.max_age_days (default 14)
- Cleanup interval: retention.cleanup_interval_minutes (default 60)

Deletion policy:
- Entire session directories older than max_age_days are deleted (mtime-based).
- No partial redaction is performed (all artifacts inside the session are removed together).

## Configuration reference

See Backend-AI/config/default.yaml for defaults.
