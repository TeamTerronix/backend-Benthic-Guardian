"""
gen_erd.py — Standalone ERD image generator.
Produces docs/images/03_erd.png with a clean, non-overlapping layout.
Run:  python docs/gen_erd.py
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe

OUT = os.path.join(os.path.dirname(__file__), "images", "03_erd.png")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

# ── Colour palette ────────────────────────────────────────────────────────────
C = {
    "users":   "#1D4ED8",
    "ng":      "#0891B2",
    "ung":     "#6366F1",
    "sensors": "#059669",
    "reads":   "#D97706",
    "preds":   "#7C3AED",
    "bg":      "#F0F4FF",
    "row_a":   "#DBEAFE",
    "row_b":   "#EFF6FF",
    "border":  "#1e3a5f",
    "text":    "#111827",
    "grey":    "#6B7280",
    "arrow":   "#374151",
    "note":    "#F5F3FF",
}

FIG_W, FIG_H = 20, 13

fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
fig.patch.set_facecolor(C["bg"])
ax.set_facecolor(C["bg"])

# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(FIG_W/2, 12.6,
        "SLIOT — Database Entity Relationship Diagram",
        fontsize=17, fontweight="bold", ha="center", va="center",
        color=C["border"])
ax.text(FIG_W/2, 12.2,
        "PostgreSQL (Supabase)   ·   6 tables   ·   SQLAlchemy ORM",
        fontsize=10, ha="center", va="center", color=C["grey"])

# ═════════════════════════════════════════════════════════════════════════════
# TABLE DRAWING HELPER
# Returns a dict with anchor points: top, bottom, left, right, mid_y
# ═════════════════════════════════════════════════════════════════════════════
ROW_H   = 0.36
HDR_H   = 0.52
PAD     = 0.06
TBL_W   = 4.0

def draw_table(ax, left, top, title, fields, color):
    """
    fields: list of (col_name, type_str, tag)
      tag: "PK", "FK", "PK,FK", or ""
    Returns anchor dict.
    """
    n = len(fields)
    total_h = HDR_H + n * ROW_H + PAD * 2

    # Drop shadow
    shadow = FancyBboxPatch(
        (left + 0.07, top - total_h - 0.07), TBL_W, total_h,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        linewidth=0, facecolor="#00000022", zorder=1)
    ax.add_patch(shadow)

    # Header
    hdr = FancyBboxPatch(
        (left, top - HDR_H), TBL_W, HDR_H,
        boxstyle="round,pad=0.04,rounding_size=0.12",
        linewidth=1.6, edgecolor=C["border"],
        facecolor=color, zorder=3)
    ax.add_patch(hdr)
    ax.text(left + TBL_W/2, top - HDR_H/2,
            title, ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="white", zorder=5)

    # Rows background (white card)
    body = FancyBboxPatch(
        (left, top - HDR_H - n * ROW_H - PAD * 2),
        TBL_W, n * ROW_H + PAD * 2,
        boxstyle="square,pad=0",
        linewidth=1.6, edgecolor=C["border"],
        facecolor="white", zorder=2)
    ax.add_patch(body)

    for i, (col, typ, tag) in enumerate(fields):
        ry   = top - HDR_H - PAD - (i + 0.5) * ROW_H
        rowbg = C["row_a"] if i % 2 == 0 else C["row_b"]
        rbg  = mpatches.Rectangle(
            (left + 0.04, top - HDR_H - PAD - (i + 1) * ROW_H + 0.02),
            TBL_W - 0.08, ROW_H - 0.02,
            linewidth=0, facecolor=rowbg, zorder=3)
        ax.add_patch(rbg)

        # Tag badge
        if tag:
            badge_col  = "#FBBF24" if "PK" in tag else "#34D399"
            badge_text = tag
            bw = 0.62 if "," in tag else 0.36
            badge = FancyBboxPatch(
                (left + 0.09, ry - 0.13), bw, 0.26,
                boxstyle="round,pad=0.03,rounding_size=0.06",
                linewidth=0, facecolor=badge_col, zorder=5)
            ax.add_patch(badge)
            ax.text(left + 0.09 + bw/2, ry,
                    badge_text, ha="center", va="center",
                    fontsize=5.8, fontweight="bold", color="#1e3a5f", zorder=6)
            col_x = left + 0.09 + bw + 0.08
        else:
            col_x = left + 0.12

        ax.text(col_x, ry, col,
                ha="left", va="center",
                fontsize=8.5, color=C["text"], zorder=5)
        ax.text(left + TBL_W - 0.10, ry, typ,
                ha="right", va="center",
                fontsize=7.5, color=C["grey"], style="italic", zorder=5)

    bottom = top - total_h
    return dict(
        left   = left,
        right  = left + TBL_W,
        top    = top,
        bottom = bottom,
        mid_x  = left + TBL_W / 2,
        mid_y  = (top + bottom) / 2,
    )


# ═════════════════════════════════════════════════════════════════════════════
# LAYOUT  (carefully spaced so arrows never cross table bodies)
#
#  Row A (top):    users  |  network_groups  |  user_network_groups
#  Row B (middle): sensors
#  Row C (bottom): sensor_readings  |  predictions
#
# Gap between rows is wide enough for clean horizontal+vertical arrows.
# ═════════════════════════════════════════════════════════════════════════════

COL1_L = 0.6
COL2_L = 5.8
COL3_L = 11.2
COL4_L = 15.4       # predictions

ROW_A_TOP = 11.7
ROW_B_TOP =  7.9
ROW_C_TOP =  4.3

# ── users (top-left) ──────────────────────────────────────────────────────────
users = draw_table(ax, COL1_L, ROW_A_TOP, "users", [
    ("id",              "INTEGER",     "PK"),
    ("email",           "VARCHAR",     ""),
    ("hashed_password", "VARCHAR",     ""),
    ("role",            "ENUM",        ""),
    ("created_at",      "TIMESTAMPTZ", ""),
], C["users"])

# ── network_groups (top-centre) ───────────────────────────────────────────────
ng = draw_table(ax, COL2_L, ROW_A_TOP, "network_groups", [
    ("id",         "VARCHAR",     "PK"),
    ("name",       "VARCHAR",     ""),
    ("created_at", "TIMESTAMPTZ", ""),
], C["ng"])

# ── user_network_groups (top-right, join table) ───────────────────────────────
ung = draw_table(ax, COL3_L, ROW_A_TOP, "user_network_groups", [
    ("user_id",          "INTEGER", "PK,FK"),
    ("network_group_id", "VARCHAR", "PK,FK"),
    ("created_at",       "TIMESTAMPTZ", ""),
], C["ung"])

# ── sensors (middle) ──────────────────────────────────────────────────────────
sensors = draw_table(ax, COL1_L, ROW_B_TOP, "sensors", [
    ("id",               "INTEGER", "PK"),
    ("sensor_uid",       "VARCHAR", ""),
    ("owner_id",         "INTEGER", "FK"),
    ("network_group_id", "VARCHAR", "FK"),
    ("latitude",         "FLOAT",   ""),
    ("longitude",        "FLOAT",   ""),
    ("depth",            "FLOAT",   ""),
    ("is_approved",      "BOOLEAN", ""),
    ("created_at",       "TIMESTAMPTZ", ""),
], C["sensors"])

# ── sensor_readings (bottom-left) ────────────────────────────────────────────
readings = draw_table(ax, COL2_L, ROW_C_TOP, "sensor_readings", [
    ("id",          "INTEGER",     "PK"),
    ("sensor_id",   "INTEGER",     "FK"),
    ("timestamp",   "TIMESTAMPTZ", ""),
    ("temperature", "FLOAT",       ""),
    ("created_at",  "TIMESTAMPTZ", ""),
], C["reads"])

# ── predictions (bottom-right) ───────────────────────────────────────────────
predictions = draw_table(ax, COL4_L, ROW_C_TOP, "predictions", [
    ("id",               "INTEGER",     "PK"),
    ("sensor_id",        "INTEGER",     "FK"),
    ("target_timestamp", "TIMESTAMPTZ", ""),
    ("predicted_temp",   "FLOAT",       ""),
    ("risk_level",       "INTEGER",     ""),
    ("risk_score",       "FLOAT",       ""),
    ("anomaly",          "FLOAT",       ""),
    ("days_stressed",    "INTEGER",     ""),
    ("warming_rate",     "FLOAT",       ""),
    ("physics_residual", "FLOAT",       ""),
    ("created_at",       "TIMESTAMPTZ", ""),
], C["preds"])


# ═════════════════════════════════════════════════════════════════════════════
# RELATIONSHIP ARROWS — all routed along the outside/between tables
# ═════════════════════════════════════════════════════════════════════════════

def rel(ax, x1, y1, x2, y2, label="1:N", lw=1.8,
        color="#374151", rad=0.0, label_dx=0.08, label_dy=0.12):
    ax.annotate("",
        xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color, lw=lw,
            connectionstyle=f"arc3,rad={rad}",
            shrinkA=5, shrinkB=5,
        ), zorder=6)
    mx = (x1 + x2) / 2
    my = (y1 + y2) / 2
    ax.text(mx + label_dx, my + label_dy, label,
            fontsize=8, fontweight="bold", color=color, zorder=7,
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white",
                      edgecolor=color, linewidth=0.8, alpha=0.9))

# 1. users → user_network_groups   (right edge of users → left edge of ung)
#    Route: go right from users.right at users.mid_y, then to ung.left at ung row 0
rel(ax,
    users["right"], users["mid_y"],
    ung["left"],    ung["mid_y"] + 0.55,
    label="1:N", color=C["users"], rad=0.0,
    label_dx=0.1, label_dy=0.14)

# 2. network_groups → user_network_groups
rel(ax,
    ng["right"],    ng["mid_y"],
    ung["left"],    ung["mid_y"] - 0.18,
    label="1:N", color=C["ng"], rad=0.0,
    label_dx=0.1, label_dy=0.14)

# 3. users → sensors  (straight down, left side)
rel(ax,
    users["mid_x"] - 0.3, users["bottom"],
    sensors["mid_x"] - 0.3, sensors["top"],
    label="1:N  (owner)", color=C["users"], rad=0.0,
    label_dx=0.12, label_dy=0.10)

# 4. network_groups → sensors  (diagonal: ng bottom → sensors.right)
rel(ax,
    ng["mid_x"], ng["bottom"],
    sensors["right"], sensors["mid_y"],
    label="1:N", color=C["ng"], rad=-0.25,
    label_dx=0.35, label_dy=0.08)

# 5. sensors → sensor_readings  (sensors.right → readings.left, horizontal)
rel(ax,
    sensors["right"],  sensors["mid_y"] + 0.5,
    readings["left"],  readings["top"] - 0.55,
    label="1:N", color=C["sensors"], rad=0.0,
    label_dx=0.12, label_dy=0.18)

# 6. sensors → predictions  (sensors.right → predictions.left)
rel(ax,
    sensors["right"],      sensors["mid_y"] - 0.7,
    predictions["left"],   predictions["top"] - 1.0,
    label="1:N", color=C["sensors"], rad=-0.08,
    label_dx=0.15, label_dy=0.18)


# ═════════════════════════════════════════════════════════════════════════════
# CARDINALITY NOTATION LEGEND (bottom-left)
# ═════════════════════════════════════════════════════════════════════════════
leg_tables = [
    (C["users"],   "users"),
    (C["ng"],      "network_groups"),
    (C["ung"],     "user_network_groups  (join table)"),
    (C["sensors"], "sensors"),
    (C["reads"],   "sensor_readings"),
    (C["preds"],   "predictions"),
]
handles = [mpatches.Patch(color=c, label=l) for c, l in leg_tables]
ax.legend(handles=handles, loc="lower left",
          fontsize=8.5, framealpha=0.95, edgecolor=C["border"],
          ncol=3, bbox_to_anchor=(0.01, 0.01))

# Badge key
for bx, (bc, bt) in enumerate(
        [("#FBBF24", "PK  Primary Key"),
         ("#34D399", "FK  Foreign Key")]):
    badge = FancyBboxPatch((COL1_L + bx * 2.5, 0.22), 2.2, 0.40,
                            boxstyle="round,pad=0.05",
                            facecolor=bc, linewidth=0, zorder=4)
    ax.add_patch(badge)
    ax.text(COL1_L + bx * 2.5 + 1.1, 0.42, bt,
            ha="center", va="center",
            fontsize=8.5, fontweight="bold", color="#1e3a5f", zorder=5)

plt.tight_layout(pad=0.3)
fig.savefig(OUT, dpi=180, bbox_inches="tight")
plt.close(fig)
print(f"Saved -> {OUT}")
