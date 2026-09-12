"""
report_export.py
================
Server-side CSV and JSON builders for Benthic Guardian report downloads.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any


PRODUCT_NAME = "Benthic Guardian"


def filter_report_datasets(
    report: dict[str, Any],
    *,
    include_sst: bool = True,
    include_dhw: bool = True,
    include_predictions: bool = True,
    include_metadata: bool = True,
) -> dict[str, Any]:
    """Return a copy of the report with selected datasets / metadata."""
    datasets = report.get("datasets") or {}
    summary = dict(report.get("summary") or {})
    filtered_datasets: dict[str, list] = {
        "sst": list(datasets.get("sst") or []) if include_sst else [],
        "dhw": list(datasets.get("dhw") or []) if include_dhw else [],
        "predictions": list(datasets.get("predictions") or []) if include_predictions else [],
    }
    summary["total_readings"] = len(filtered_datasets["sst"])
    summary["total_dhw"] = len(filtered_datasets["dhw"])
    summary["total_predictions"] = len(filtered_datasets["predictions"])

    meta = dict(report.get("metadata") or {})
    meta["product"] = PRODUCT_NAME
    if not include_metadata:
        # Keep only minimal export identity fields
        meta = {
            "product": PRODUCT_NAME,
            "format": meta.get("format"),
            "generated_at": meta.get("generated_at"),
        }

    return {
        "summary": summary,
        "risk_summary": report.get("risk_summary") or {},
        "datasets": filtered_datasets,
        "metadata": meta,
    }


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    else:
        text = str(value)
    # Mitigate CSV formula injection in spreadsheet apps
    if text[:1] in ("=", "+", "-", "@"):
        text = "'" + text
    return text


def build_report_csv(report: dict[str, Any]) -> bytes:
    """
    Flatten datasets into one CSV with a ``dataset`` column.
    Metadata is written as leading ``# key: value`` comment lines.
    """
    datasets = report.get("datasets") or {}
    meta = report.get("metadata") or {}
    groups: list[tuple[str, list[dict[str, Any]]]] = [
        ("sst", list(datasets.get("sst") or [])),
        ("dhw", list(datasets.get("dhw") or [])),
        ("predictions", list(datasets.get("predictions") or [])),
    ]

    flattened: list[dict[str, Any]] = []
    for name, rows in groups:
        for row in rows:
            flattened.append({"dataset": name, **row})

    columns: list[str] = []
    seen: set[str] = set()
    for row in flattened:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                columns.append(key)

    buf = io.StringIO(newline="")
    # UTF-8 BOM helps Excel open the file correctly
    buf.write("\ufeff")
    buf.write(f"# product: {PRODUCT_NAME}\r\n")
    for key, value in meta.items():
        buf.write(f"# {key}: {value}\r\n")
    buf.write(f"# row_count: {len(flattened)}\r\n")

    writer = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    if columns:
        writer.writerow(columns)
        for row in flattened:
            writer.writerow([_csv_cell(row.get(col)) for col in columns])
    else:
        writer.writerow(["dataset"])
        writer.writerow(["(no rows)"])

    return buf.getvalue().encode("utf-8")


def build_report_json(report: dict[str, Any]) -> bytes:
    """Pretty-printed JSON export bytes (UTF-8)."""
    payload = {
        "product": PRODUCT_NAME,
        "summary": report.get("summary") or {},
        "risk_summary": report.get("risk_summary") or {},
        "metadata": report.get("metadata") or {},
        "data": report.get("datasets") or {},
    }
    return json.dumps(payload, indent=2, ensure_ascii=True, default=str).encode("utf-8")
