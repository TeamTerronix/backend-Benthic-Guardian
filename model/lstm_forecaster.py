"""
lstm_forecaster.py
==================
ANN–LSTM short-term forecaster (60-day SST + DHW history → +1/+3/+7 day).

Complements the PINN spatial / hourly forecaster:
  - PINN  → maps, 168-h hourly sensor forecasts
  - LSTM  → sequence short-term SST/DHW + bleaching risk
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "-1")

from prepare_data import LOCATIONS, apply_scalers, fit_scalers, load_all_locations
from utils import calculate_bleaching_risk, calculate_location_baseline

logger = logging.getLogger(__name__)

LOOKBACK = 60
HORIZONS = [1, 3, 7]

_MODEL_DIR = os.path.dirname(os.path.abspath(__file__))


class ANNLSTMForecaster:
    """Loads ANN–LSTM once and serves per-location 1/3/7-day forecasts."""

    def __init__(
        self,
        model_path: Optional[str] = None,
        dataset_dir: Optional[str] = None,
    ):
        self.model_path = model_path or os.path.join(_MODEL_DIR, "ann_lstm_L60_best.h5")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"ANN–LSTM weights not found: {self.model_path}. "
                "Copy ann_lstm_L60_best.h5 into backend/model/."
            )

        # prepare_data reads sliot_dataset relative to its own file dir
        logger.info("Loading multi-site SST/DHW history for ANN–LSTM…")
        self.df = load_all_locations()
        self.scalers = fit_scalers(self.df)
        self.df = apply_scalers(self.df, self.scalers)
        self.df = self.df.sort_values(["location", "time"]).reset_index(drop=True)

        logger.info("Loading ANN–LSTM from %s", self.model_path)
        self.model = keras.models.load_model(self.model_path, compile=False)
        self.model.trainable = False

        self.baselines: Dict[str, Dict[int, float]] = {}
        for loc in LOCATIONS:
            sst_path = os.path.join(_MODEL_DIR, "sliot_dataset", loc, "sst_full.csv")
            if os.path.exists(sst_path):
                try:
                    self.baselines[loc] = calculate_location_baseline(sst_path)
                except Exception as exc:
                    logger.warning("Baseline load failed for %s: %s", loc, exc)

        logger.info(
            "ANNLSTMForecaster ready  lookback=%d  horizons=%s  locations=%d",
            LOOKBACK,
            HORIZONS,
            len(LOCATIONS),
        )

    @staticmethod
    def _inv(scaler, vals) -> np.ndarray:
        vals = np.asarray(vals, dtype=float).reshape(-1, 1)
        fn = getattr(scaler, "feature_names_in_", None)
        if fn is not None and len(fn):
            return scaler.inverse_transform(pd.DataFrame(vals, columns=fn)).ravel()
        return scaler.inverse_transform(vals).ravel()

    def get_history_window(
        self, location: str, as_of: Optional[datetime] = None, lookback: int = LOOKBACK
    ) -> pd.DataFrame:
        location = location.lower().strip()
        g = self.df[self.df["location"] == location].sort_values("time")
        if g.empty:
            raise ValueError(f"Unknown location: {location}. Choose from {LOCATIONS}")

        if as_of is not None:
            ts = pd.Timestamp(as_of)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            else:
                ts = ts.tz_convert("UTC")
            g = g[g["time"] <= ts]

        if len(g) < lookback:
            raise ValueError(
                f"Need {lookback} days of history for {location}, found {len(g)}."
            )
        return g.iloc[-lookback:].copy()

    def forecast(
        self,
        location: str,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Returns list of dicts for horizons +1, +3, +7 days.
        """
        location = location.lower().strip()
        window = self.get_history_window(location, as_of=as_of, lookback=LOOKBACK)
        issue_row = window.iloc[-1]
        issue_time = issue_row["time"]
        sst_issue = float(issue_row["analysed_sst"])
        dhw_issue = float(issue_row["degree_heating_week"])

        X = np.stack(
            [window["temp_norm"].values, window["dhw_norm"].values],
            axis=-1,
        ).astype(np.float32)[None, ...]

        pred_n = np.asarray(self.model.predict(X, verbose=0)).reshape(1, -1)
        month = int(pd.Timestamp(issue_time).month)
        baseline = self.baselines.get(location, {}).get(month, 28.0)

        rows: List[Dict[str, Any]] = []
        for k, h in enumerate(HORIZONS):
            sst = float(self._inv(self.scalers["scaler_temp"], pred_n[:, 2 * k])[0])
            dhw = float(self._inv(self.scalers["scaler_dhw"], pred_n[:, 2 * k + 1])[0])
            dhw = max(0.0, dhw)

            risk = calculate_bleaching_risk(
                current_temp=sst,
                baseline_temp=baseline,
                recent_temps=list(window["analysed_sst"].values[-12:]) + [sst],
                dhw=dhw,
            )
            level_name = {0: "Healthy", 1: "Warning", 2: "Danger"}[risk["risk_level"]]
            target = pd.Timestamp(issue_time) + pd.Timedelta(days=h)

            rows.append(
                {
                    "model": "ann_lstm_L60",
                    "location": location,
                    "issue_time": pd.Timestamp(issue_time).isoformat(),
                    "horizon_days": h,
                    "target_timestamp": target.to_pydatetime()
                    if hasattr(target, "to_pydatetime")
                    else target,
                    "target_date": target.isoformat(),
                    "sst_issue": round(sst_issue, 3),
                    "dhw_issue": round(dhw_issue, 3),
                    "predicted_temp": round(sst, 3),
                    "sst_pred": round(sst, 3),
                    "dhw_pred": round(dhw, 3),
                    "sst_persist": round(sst_issue, 3),
                    "baseline_month_sst": round(baseline, 3),
                    "anomaly": round(float(risk["anomaly"]), 3),
                    "risk_score": round(float(risk["risk_score"]), 3),
                    "risk_level": int(risk["risk_level"]),
                    "risk_name": level_name,
                    "days_stressed": risk.get("days_stressed"),
                    "warming_rate": risk.get("warming_rate"),
                }
            )
        return rows


_lstm: Optional[ANNLSTMForecaster] = None


def get_lstm_forecaster() -> ANNLSTMForecaster:
    global _lstm
    if _lstm is None:
        _lstm = ANNLSTMForecaster()
    return _lstm
