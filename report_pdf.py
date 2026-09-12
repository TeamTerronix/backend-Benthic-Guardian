"""
report_pdf.py
=============
Server-side PDF report builder for Benthic Guardian.

Uses ReportLab to produce a branded, production-style PDF with:
  - product colours (navy / cyan / teal)
  - logo mark
  - aligned tables with truncated cells (no overflow)
  - summary metrics, risk breakdown, and sample data tables

Product name in the PDF is always "Benthic Guardian" (never SLIOT).
"""

from __future__ import annotations

import io
import os
from datetime import datetime
from typing import Any, Iterable, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand theme (matches dashboard dark accents) ─────────────────────────────
NAVY = colors.HexColor("#0B1120")
SURFACE = colors.HexColor("#131B2E")
ELEVATED = colors.HexColor("#1A2540")
CYAN = colors.HexColor("#00E5FF")
TEAL = colors.HexColor("#1DE9B6")
AMBER = colors.HexColor("#FFB300")
CORAL = colors.HexColor("#FF5252")
INK = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#64748B")
SOFT = colors.HexColor("#F1F5F9")
SOFT_ALT = colors.HexColor("#E2E8F0")
WHITE = colors.white
LINE = colors.HexColor("#CBD5E1")

PRODUCT_NAME = "Benthic Guardian"
TEAM_NAME = "Team Terronix"
MAX_TABLE_ROWS = 35
PAGE_W, PAGE_H = A4
MARGIN = 16 * mm

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "assets", "benthic-guardian-logo.png")


def _clip(value: Any, max_len: int = 36) -> str:
    if value is None:
        return "—"
    text = " ".join(str(value).split())
    if not text:
        return "—"
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def _fmt_dt(value: Optional[str]) -> str:
    if not value:
        return "—"
    try:
        raw = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%d %b %Y  %H:%M UTC")
    except Exception:
        return _clip(value, 28)


def _fmt_num(value: Any, digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "—"


def _risk_name(level: Any) -> str:
    try:
        n = int(level)
    except (TypeError, ValueError):
        return "—"
    return {0: "Healthy", 1: "Warning", 2: "Danger"}.get(n, "—")


def _share(part: Any, total: Any) -> str:
    try:
        t = int(total or 0)
        p = int(part or 0)
    except (TypeError, ValueError):
        return "—"
    if t <= 0:
        return "0%"
    return f"{(100.0 * p / t):.1f}%"


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "BGTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=WHITE,
            leading=22,
        ),
        "subtitle": ParagraphStyle(
            "BGSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=CYAN,
            leading=12,
        ),
        "section": ParagraphStyle(
            "BGSection",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=6,
            leading=14,
        ),
        "body": ParagraphStyle(
            "BGBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            textColor=INK,
            leading=11,
        ),
        "muted": ParagraphStyle(
            "BGMuted",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=MUTED,
            leading=10,
        ),
        "cell": ParagraphStyle(
            "BGCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=INK,
            leading=9,
            wordWrap="CJK",
        ),
        "cell_header": ParagraphStyle(
            "BGCellHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            textColor=WHITE,
            leading=9,
        ),
        "metric_label": ParagraphStyle(
            "BGMetricLabel",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=MUTED,
            alignment=TA_CENTER,
            leading=9,
        ),
        "metric_value": ParagraphStyle(
            "BGMetricValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=INK,
            alignment=TA_CENTER,
            leading=13,
        ),
        "footer": ParagraphStyle(
            "BGFooter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def _header_table(styles: dict[str, ParagraphStyle]) -> Table:
    logo = None
    if os.path.isfile(_LOGO_PATH):
        logo = Image(_LOGO_PATH, width=14 * mm, height=14 * mm)

    left_bits: list[Any] = []
    if logo is not None:
        left_bits.append(logo)
    text_block = [
        Paragraph(PRODUCT_NAME, styles["title"]),
        Paragraph("Coral reef monitoring & bleaching risk report", styles["subtitle"]),
        Paragraph(f"{TEAM_NAME}  ·  Confidential operational export", styles["subtitle"]),
    ]
    text_tbl = Table([[b] for b in text_block], colWidths=[140 * mm])
    text_tbl.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )

    if logo is not None:
        inner = Table([[logo, text_tbl]], colWidths=[18 * mm, 152 * mm])
        inner.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        content = [[inner]]
    else:
        content = [[text_tbl]]

    banner = Table(content, colWidths=[PAGE_W - 2 * MARGIN])
    banner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                ("BOX", (0, 0), (-1, -1), 0, NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 2.5, CYAN),
            ]
        )
    )
    return banner


def _kv_table(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [
            Paragraph(_clip(k, 28), styles["cell"]),
            Paragraph(_clip(v, 70), styles["cell"]),
        ]
        for k, v in rows
    ]
    tbl = Table(data, colWidths=[45 * mm, 125 * mm])
    style_cmds: list[Any] = [
        ("BACKGROUND", (0, 0), (0, -1), SOFT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
    ]
    for i in range(len(data)):
        if i % 2 == 1:
            style_cmds.append(("BACKGROUND", (1, i), (1, i), SOFT_ALT))
    tbl.setStyle(TableStyle(style_cmds))
    return tbl


def _metric_cards(
    metrics: list[tuple[str, str]],
    styles: dict[str, ParagraphStyle],
) -> Table:
    cells = []
    for label, value in metrics:
        card = Table(
            [
                [Paragraph(_clip(label, 18), styles["metric_label"])],
                [Paragraph(_clip(value, 16), styles["metric_value"])],
            ],
            colWidths=[40 * mm],
        )
        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                    ("BOX", (0, 0), (-1, -1), 1, CYAN),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        cells.append(card)

    # pad to 4 columns
    while len(cells) < 4:
        cells.append("")
    tbl = Table([cells[:4]], colWidths=[42.5 * mm] * 4)
    tbl.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return tbl


def _data_table(
    headers: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    styles: dict[str, ParagraphStyle],
) -> Table:
    head = [Paragraph(_clip(h, 22), styles["cell_header"]) for h in headers]
    body = [
        [Paragraph(_clip(cell, 28), styles["cell"]) for cell in row]
        for row in rows
    ]
    data = [head] + body
    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    cmds: list[Any] = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("ALIGN", (1, 1), (-1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
    ]
    tbl.setStyle(TableStyle(cmds))
    return tbl


def _take(rows: Iterable[dict[str, Any]], limit: int = MAX_TABLE_ROWS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if i >= limit:
            break
        out.append(row)
    return out


def build_report_pdf(report: dict[str, Any]) -> bytes:
    """Build a branded PDF from the /api/report payload dict. Returns PDF bytes."""
    styles = _styles()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"{PRODUCT_NAME} Monitoring Report",
        author=TEAM_NAME,
        subject="Reef temperature and bleaching risk report",
    )

    summary = report.get("summary") or {}
    risk = report.get("risk_summary") or {}
    datasets = report.get("datasets") or {}
    meta = report.get("metadata") or {}

    sst_rows = list(datasets.get("sst") or [])
    dhw_rows = list(datasets.get("dhw") or [])
    pred_rows = list(datasets.get("predictions") or [])

    story: list[Any] = []
    story.append(_header_table(styles))
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Operational Monitoring Summary", styles["section"]))
    story.append(
        Paragraph(
            "This report summarises live reef temperature readings, derived heat-stress "
            "indicators (DHW), and model predictions for the selected period. Data access "
            "is scoped to the signed-in account network permissions.",
            styles["body"],
        )
    )
    story.append(Spacer(1, 4 * mm))

    # 1. Report info
    story.append(Paragraph("1. Report Information", styles["section"]))
    story.append(
        _kv_table(
            [
                ("Product", PRODUCT_NAME),
                ("Generated at", _fmt_dt(summary.get("generated_at"))),
                ("Generated by", _clip(meta.get("generated_by") or meta.get("user"), 48)),
                ("Account role", _clip(meta.get("role"), 24)),
                ("Period from", _fmt_dt(summary.get("date_from"))),
                ("Period to", _fmt_dt(summary.get("date_to"))),
                ("Export format", "PDF (server-generated)"),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 5 * mm))

    # 2. Key metrics
    story.append(Paragraph("2. Key Metrics", styles["section"]))
    story.append(
        _metric_cards(
            [
                ("Readings", str(summary.get("total_readings") or 0)),
                ("Predictions", str(summary.get("total_predictions") or 0)),
                ("Avg Temp", _fmt_num(summary.get("average_temperature"), 2, "°C")),
                ("Max Temp", _fmt_num(summary.get("max_temperature"), 2, "°C")),
            ],
            styles,
        )
    )
    story.append(Spacer(1, 5 * mm))

    # 3. Risk summary
    story.append(Paragraph("3. Bleaching Risk Summary", styles["section"]))
    risk_body = [
        [
            "Healthy (0)",
            str(risk.get("healthy") or 0),
            _share(risk.get("healthy"), risk.get("total_points")),
        ],
        [
            "Warning (1)",
            str(risk.get("warning") or 0),
            _share(risk.get("warning"), risk.get("total_points")),
        ],
        [
            "Danger (2)",
            str(risk.get("danger") or 0),
            _share(risk.get("danger"), risk.get("total_points")),
        ],
        [
            "Average risk score",
            _fmt_num(risk.get("avg_risk_score"), 4),
            "0–1 scale",
        ],
    ]
    story.append(
        _data_table(
            ["Risk Level", "Count", "Share of Predictions"],
            risk_body,
            [70 * mm, 40 * mm, 60 * mm],
            styles,
        )
    )
    story.append(Spacer(1, 5 * mm))

    # 4. Temperature sample
    story.append(Paragraph("4. Temperature Readings (sample)", styles["section"]))
    story.append(
        Paragraph(
            f"Showing up to {MAX_TABLE_ROWS} of {len(sst_rows)} reading rows "
            "(newest first). Cells are clipped to keep columns aligned.",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    sst_sample = _take(sst_rows, MAX_TABLE_ROWS)
    if sst_sample:
        story.append(
            _data_table(
                ["Time (UTC)", "Sensor", "Lat", "Lon", "Temp °C"],
                [
                    [
                        _fmt_dt(r.get("time")),
                        _clip(r.get("sensor_uid"), 16),
                        _fmt_num(r.get("latitude"), 3),
                        _fmt_num(r.get("longitude"), 3),
                        _fmt_num(r.get("temperature"), 2),
                    ]
                    for r in sst_sample
                ],
                [48 * mm, 38 * mm, 26 * mm, 26 * mm, 32 * mm],
                styles,
            )
        )
    else:
        story.append(Paragraph("No temperature readings in this period.", styles["muted"]))
    story.append(Spacer(1, 5 * mm))

    # 5. DHW sample
    story.append(Paragraph("5. Degree Heating Weeks (sample)", styles["section"]))
    story.append(
        Paragraph(
            f"Derived DHW from temperature hotspots above 30°C. "
            f"Showing up to {MAX_TABLE_ROWS} of {len(dhw_rows)} points.",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    dhw_sample = _take(dhw_rows, MAX_TABLE_ROWS)
    if dhw_sample:
        story.append(
            _data_table(
                ["Time (UTC)", "DHW"],
                [
                    [_fmt_dt(r.get("time")), _fmt_num(r.get("dhw"), 3)]
                    for r in dhw_sample
                ],
                [110 * mm, 60 * mm],
                styles,
            )
        )
    else:
        story.append(Paragraph("No DHW points in this period.", styles["muted"]))
    story.append(Spacer(1, 5 * mm))

    # 6. Predictions sample
    story.append(Paragraph("6. Model Predictions (sample)", styles["section"]))
    story.append(
        Paragraph(
            f"PINN forecast rows. Showing up to {MAX_TABLE_ROWS} of {len(pred_rows)} predictions.",
            styles["muted"],
        )
    )
    story.append(Spacer(1, 2 * mm))
    pred_sample = _take(pred_rows, MAX_TABLE_ROWS)
    if pred_sample:
        story.append(
            _data_table(
                ["Target (UTC)", "Sensor", "Temp °C", "Risk", "Score", "Anomaly"],
                [
                    [
                        _fmt_dt(r.get("target_timestamp")),
                        _clip(r.get("sensor_id"), 10),
                        _fmt_num(r.get("predicted_temp"), 2),
                        _risk_name(r.get("risk_level")),
                        _fmt_num(r.get("risk_score"), 3),
                        _fmt_num(r.get("anomaly"), 2),
                    ]
                    for r in pred_sample
                ],
                [42 * mm, 24 * mm, 26 * mm, 28 * mm, 24 * mm, 26 * mm],
                styles,
            )
        )
    else:
        story.append(
            Paragraph(
                "No prediction rows in this period. Predictions appear after the PINN "
                "forecast job has run for approved sensors with recent readings.",
                styles["muted"],
            )
        )
    story.append(Spacer(1, 8 * mm))

    # Notes
    story.append(Paragraph("7. Notes", styles["section"]))
    notes = [
        f"• Product brand: {PRODUCT_NAME} by {TEAM_NAME}.",
        "• PDF is generated on the API server (not in the browser) for consistent branding and safer handling of report data.",
        "• Risk levels: 0 = Healthy, 1 = Warning, 2 = Danger (bleaching risk).",
        "• Large datasets are sampled in this PDF; use CSV/JSON export for full raw tables.",
        "• Temperature unit is degrees Celsius (°C). Timestamps are shown in UTC.",
    ]
    for note in notes:
        story.append(Paragraph(note, styles["muted"]))
        story.append(Spacer(1, 1.5 * mm))

    def _on_page(canvas, doc_):
        canvas.saveState()
        # top accent line
        canvas.setStrokeColor(CYAN)
        canvas.setLineWidth(1.2)
        canvas.line(MARGIN, PAGE_H - 10 * mm, PAGE_W - MARGIN, PAGE_H - 10 * mm)
        # footer
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        footer = (
            f"{PRODUCT_NAME}  ·  Page {doc_.page}  ·  "
            f"Generated { _fmt_dt(summary.get('generated_at')) }"
        )
        canvas.drawCentredString(PAGE_W / 2, 10 * mm, footer)
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
        canvas.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buffer.getvalue()
