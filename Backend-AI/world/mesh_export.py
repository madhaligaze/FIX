from __future__ import annotations


def env_mesh_obj_bytes(world_model) -> bytes:
    """
    Robust OBJ export as bytes for SessionStore.save_bytes().
    Supports either:
      - world_model.export_env_mesh_obj_bytes() -> bytes
      - world_model.export_env_mesh_obj() -> str
    """
    fn_b = getattr(world_model, "export_env_mesh_obj_bytes", None)
    if callable(fn_b):
        out = fn_b()
        if isinstance(out, (bytes, bytearray)):
            return bytes(out)

    fn_s = getattr(world_model, "export_env_mesh_obj", None)
    if callable(fn_s):
        s = fn_s()
        if isinstance(s, str):
            return s.encode("utf-8")

    # last resort: empty but valid bytes
    return b"# empty obj\n"
