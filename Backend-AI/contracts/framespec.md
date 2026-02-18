# Coordinate Frames Specification (FIX)

This document freezes the coordinate conventions for FramePacket and all derived geometry.
Any change here MUST bump FramePacket version and add a migration.

## Frames

1) `camera` frame (C)
   - Origin: camera optical center
   - Axes (right-handed):
     - +X: image right
     - +Y: image down
     - +Z: forward (out of camera)
   - Pixel to ray uses intrinsics `(fx, fy, cx, cy)` in pixels.

2) `world` frame (W)
   - Global frame produced by AR tracking (ARCore world coordinates).
   - Right-handed.
   - Units: meters.

3) `gravity_aligned` frame (G) (optional)
   - Same origin as `world`, rotated so +Y is aligned with gravity "up".
   - Used for floor/wall reasoning and stable UI.

4) `target_box` frame (T)
   - Local frame aligned with the "work zone" (scaffold working volume).
   - Defined by anchors/bounds; used to compute coverage/readiness in a stable volume.

## Pose conventions

FramePacket provides camera pose as a transform from camera to world:
  - `T_WC`: transforms a point in camera coordinates into world coordinates.

Representation:
  - `pose.position` = (x, y, z) in meters, in world frame.
  - `pose.quaternion` = (qx, qy, qz, qw), unit quaternion, camera->world rotation.

Applying pose:
  - p_W = R_WC * p_C + t_WC

Quaternion rules:
  - Must be normalized (||q|| = 1).
  - If norm is near zero => invalid packet.
  - (q and -q) represent same rotation; normalization may flip sign for consistency.

## Intrinsics conventions

Intrinsics are pinhole camera parameters:
  - fx, fy: focal length in pixels
  - cx, cy: principal point in pixels
  - width, height: image dimensions in pixels

Validation:
  - fx > 0, fy > 0
  - 0 <= cx < width, 0 <= cy < height
  - width/height must match actual RGB (and depth if aligned)

## Depth conventions

Depth is an aligned depth image (same viewpoint as RGB) unless otherwise specified.
  - Encoding: uint16
  - `depth_meta.scale_m_per_unit`: meters per depth unit

Valid ranges:
  - scale must be finite and > 0
  - depth values of 0 are treated as "missing"

## Axis order and handedness

All derived geometry MUST assume:
  - Camera frame is right-handed with +Z forward.
  - World frame is right-handed in meters.
If the AR provider uses a different convention, convert at the client BEFORE sending FramePacket.

## Stability requirements

Tracking drift/jumps:
  - Backend may mark tracking_quality BAD and refuse planning/locking.
  - Packet contract remains the same; quality is assessed server-side.
