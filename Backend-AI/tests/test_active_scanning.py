from modules.active_scanning import propose_views


def test_propose_views_clusters_and_views():
    suggestions = [
        {"point": {"x": 0.0, "y": 0.0, "z": 0.0}, "reason": "model_missing", "severity": 1.0},
        {"point": {"x": 0.2, "y": 0.1, "z": 0.0}, "reason": "depth_mismatch", "severity": 0.6},
        {"point": {"x": 5.0, "y": 0.0, "z": 0.0}, "reason": "model_missing", "severity": 0.8},
    ]

    plan = propose_views(suggestions, current_pose=[1, 0, 0, 0, 0, 0, 1], max_views=2)
    assert "clusters" in plan
    assert "next_best_views" in plan
    assert len(plan["clusters"]) >= 2
    assert len(plan["next_best_views"]) == 2
