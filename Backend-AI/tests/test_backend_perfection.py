import importlib.util
import pathlib
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_module(name: str, rel_path: str):
    path = ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


cache_mod = load_module("cache_manager", "modules/cache_manager.py")
monitoring_mod = load_module("monitoring", "modules/monitoring.py")
validators_mod = load_module("validators", "modules/validators.py")


CacheManager = cache_mod.CacheManager
cached = cache_mod.cached
PerformanceMonitor = monitoring_mod.PerformanceMonitor
monitor_performance = monitoring_mod.monitor_performance
Point3D = validators_mod.Point3D
SessionUpdateAction = validators_mod.SessionUpdateAction
validate_structure_stability = validators_mod.validate_structure_stability


def test_cache_manager_ttl():
    cache = CacheManager(default_ttl=1)
    cache.set("a", 123)
    assert cache.get("a") == 123
    time.sleep(1.1)
    assert cache.get("a") is None


def test_cached_decorator_uses_cache():
    state = {"calls": 0}

    @cached(ttl=60)
    def expensive(x):
        state["calls"] += 1
        return x * 2

    assert expensive(3) == 6
    assert expensive(3) == 6
    assert state["calls"] == 1


def test_validators_action_and_structure():
    add = SessionUpdateAction(
        action="ADD",
        element_data={
            "type": "ledger",
            "start": {"x": 0, "y": 0, "z": 0},
            "end": {"x": 1, "y": 0, "z": 0},
        },
    )
    assert add.action == "ADD"
    assert isinstance(add.element_data.start, Point3D)

    result = validate_structure_stability([
        {
            "id": "b1",
            "type": "ledger",
            "start": {"x": 0, "y": 0, "z": 0},
            "end": {"x": 1, "y": 0, "z": 0},
        }
    ])
    assert result["is_valid"] is True


def test_monitor_performance_records_metrics():
    monitor = PerformanceMonitor()
    monitor.record_time("op", 0.01)
    stats = monitor.get_stats()
    assert stats["op"]["count"] == 1

    @monitor_performance("sample_op")
    def func():
        return "ok"

    assert func() == "ok"
