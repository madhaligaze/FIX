import json

from fastapi.testclient import TestClient

from main import app


def test_request_scaffold_returns_409_when_not_ready():
    client = TestClient(app)
    session_id = client.post("/session/create").json()["session_id"]
    meta = {
        "session_id": session_id,
        "frame_id": "f1",
        "timestamp": 1.0,
        "intrinsics": {"fx": 100, "fy": 100, "cx": 1, "cy": 1, "width": 2, "height": 2},
        "pose": {"position": [0, 0, 0], "quaternion": [0, 0, 0, 1]},
        "depth_meta": {"width": 2, "height": 2, "scale_m_per_unit": 0.001},
    }
    files = {
        "meta": ("meta.json", json.dumps(meta), "application/json"),
        "rgb": ("rgb.jpg", b"jpeg", "image/jpeg"),
        "depth": ("depth.u16", (0).to_bytes(2, "little") * 4, "application/octet-stream"),
    }
    post = client.post("/session/frame", files=files)
    assert post.status_code == 200
    res = client.post(f"/session/{session_id}/request_scaffold")
    assert res.status_code == 409
    assert res.json()["detail"]["status"] == "NEEDS_SCAN"
