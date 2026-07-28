"""Scheduler helper unit tests (no PINN load)."""

from types import SimpleNamespace

from scheduler import _infer_location_from_sensor


def test_infer_location_from_uid():
    sensor = SimpleNamespace(latitude=None, longitude=None, sensor_uid="node_kalpitiya_01")
    assert _infer_location_from_sensor(sensor) == "kalpitiya"


def test_infer_location_default_hikkaduwa():
    sensor = SimpleNamespace(latitude=None, longitude=None, sensor_uid="esp32_unknown")
    assert _infer_location_from_sensor(sensor) == "hikkaduwa"


def test_infer_location_from_coordinates():
    sensor = SimpleNamespace(latitude=6.12, longitude=80.08, sensor_uid="x")
    assert _infer_location_from_sensor(sensor) == "hikkaduwa"
