"""ANN–LSTM endpoint tests with mocked forecaster (no TensorFlow in CI)."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import main as main_module
from models import Sensor


@pytest.fixture
def mock_lstm(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.forecast.return_value = [
        {
            "model": "ann_lstm_L60",
            "location": "hikkaduwa",
            "issue_time": "2024-01-01T00:00:00+00:00",
            "horizon_days": 1,
            "target_date": "2024-01-02",
            "sst_issue": 28.0,
            "dhw_issue": 0.5,
            "predicted_temp": 28.2,
            "sst_pred": 28.2,
            "dhw_pred": 0.6,
            "sst_persist": 28.0,
            "baseline_month_sst": 27.5,
            "anomaly": 0.7,
            "risk_score": 0.2,
            "risk_level": 0,
            "risk_name": "healthy",
        }
    ]
    monkeypatch.setattr(main_module, "_get_lstm", lambda: fake)
    return fake


def test_lstm_forecast_requires_auth(client: TestClient):
    assert client.get("/api/lstm-forecast").status_code == 401


def test_lstm_forecast_ok(
    client: TestClient,
    auth_headers: dict[str, str],
    mock_lstm: MagicMock,
):
    response = client.get(
        "/api/lstm-forecast",
        headers=auth_headers,
        params={"location": "hikkaduwa"},
    )
    assert response.status_code == 200, response.text
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["model"] == "ann_lstm_L60"
    assert rows[0]["horizon_days"] == 1
    assert rows[0]["predicted_temp"] == 28.2
    mock_lstm.forecast.assert_called_once()


def test_lstm_forecast_missing_weights(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    def boom() -> None:
        raise FileNotFoundError("ANN–LSTM weights not found")

    monkeypatch.setattr(main_module, "_get_lstm", boom)
    response = client.get("/api/lstm-forecast", headers=auth_headers)
    assert response.status_code == 503


def test_sensor_lstm_forecast(
    client: TestClient,
    auth_headers: dict[str, str],
    approved_sensor: Sensor,
    mock_lstm: MagicMock,
):
    response = client.get(
        f"/sensors/{approved_sensor.id}/lstm-forecast",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()[0]["location"] == "hikkaduwa"
