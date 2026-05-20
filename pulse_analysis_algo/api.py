"""Transport-agnostic entrypoint for the heavy pulse-analysis math.

This module is the single boundary that worker processes call across the
ProcessPool. It must not import Django, must not perform I/O on behalf of
callers, and must accept and return picklable types only.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional, Union

import numpy as np
import pandas as pd


SignalInput = Union[str, list, tuple, np.ndarray, pd.Series, pd.DataFrame]


class AnalysisError(Exception):
    """Raised when input is unanalyzable. Distinct from infrastructure errors."""


@dataclass(frozen=True)
class AnalysisResult:
    primary: str
    secondary: str
    tertiary: str
    quaternary: str
    quinary: Optional[str]
    extras: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = asdict(self)
        flat = {k: out[k] for k in ("primary", "secondary", "tertiary", "quaternary", "quinary")}
        flat.update(out["extras"])
        return flat


def _coerce(signal_data: SignalInput) -> np.ndarray:
    if isinstance(signal_data, str):
        try:
            parsed = json.loads(signal_data)
            if isinstance(parsed, dict):
                parsed = list(parsed.values())
            signal_data = parsed
        except json.JSONDecodeError:
            try:
                signal_data = [float(x) for x in signal_data.split(",")]
            except ValueError as exc:
                raise AnalysisError(
                    "string input is not JSON or comma-separated floats"
                ) from exc
    if isinstance(signal_data, (list, tuple, pd.Series)):
        return np.array(signal_data)
    if isinstance(signal_data, np.ndarray):
        return signal_data
    if isinstance(signal_data, pd.DataFrame):
        return signal_data.values
    raise AnalysisError(f"unsupported signal input type: {type(signal_data)!r}")


def run_analysis(signal_data: SignalInput) -> AnalysisResult:
    """Run the full pulse-prediction pipeline on a raw signal.

    Safe to invoke inside a ProcessPoolExecutor: no Django, no global state,
    no file handles passed in.
    """
    from pulse_analysis_algo.Testing_function import pulse_predict

    pulse_array = _coerce(signal_data)
    prediction = pulse_predict(pulse_array)

    if not isinstance(prediction, pd.DataFrame) or prediction.empty:
        raise AnalysisError("pulse_predict returned no usable rows (Retake)")

    row = prediction.iloc[0]
    heart_yin = row.get("Heart_yin")
    if isinstance(heart_yin, str) and heart_yin.endswith("%"):
        try:
            heart_yin = float(heart_yin.rstrip("%"))
        except ValueError:
            pass

    extras: dict[str, Any] = {
        "heart_rate": row.get("Heart_rate"),
        "heart_yin": heart_yin,
        "carbohydrate": row.get("Carbohydrate"),
        "protein": row.get("Protein"),
        "fat": row.get("Fat"),
        "wind_yin": row.get("Wind_Yin"),
        "wind_yang": row.get("Wind_Yang"),
        "heat_yin": row.get("Heat_Yin"),
        "heat_yang": row.get("Heat_Yang"),
        "humid_yin": row.get("Humid_Yin"),
        "humid_yang": row.get("Humid_Yang"),
        "dry_yin": row.get("Dry_Yin"),
        "dry_yang": row.get("Dry_Yang"),
        "cold_yin": row.get("Cold_Yin"),
        "cold_yang": row.get("Cold_Yang"),
        "vata": row.get("VATA"),
        "pitta": row.get("PITTA"),
        "kapha": row.get("KAPHA"),
    }
    return AnalysisResult(
        primary=str(row["Primary"]),
        secondary=str(row["Secondary"]),
        tertiary=str(row["Tertiary"]),
        quaternary=str(row["Quaternary"]),
        quinary=None if pd.isna(row.get("Quinary")) else str(row["Quinary"]),
        extras={k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in extras.items()},
    )
