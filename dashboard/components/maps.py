"""Interactive Folium Map Component for Territory Intelligence BI Platform.

Renders real Uber H3 hexagonal polygon boundaries using H3 4.x APIs:
- Converts stored H3 cell IDs to polygon coordinates using h3.cell_to_boundary(cell_id).
- Color-codes zones deterministically by owner, takeover intensity, or activity score.
- Implements zone tooltips, popups, and layer controls.
- Optimized for sub-second rendering without loading raw GPS points.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import folium
import h3
import numpy as np
import pandas as pd
from streamlit_folium import st_folium

from dashboard.services.metrics import get_runner_color

logger = logging.getLogger(__name__)

# Chicago Loop default center
DEFAULT_CENTER_LAT = 41.8781
DEFAULT_CENTER_LON = -87.6298
DEFAULT_ZOOM = 13
MAX_HEXAGONS_CAP = 1000

# Sequential color gradients for Heatmaps & Contested zones
HOTSPOT_GRADIENT = [
    (0.0, "#0F172A"),
    (0.2, "#0284C7"),
    (0.4, "#06B6D4"),
    (0.6, "#10B981"),
    (0.8, "#F59E0B"),
    (1.0, "#EF4444"),
]

CONTESTED_GRADIENT = [
    (0.0, "#1E293B"),
    (0.25, "#7C3AED"),
    (0.50, "#D946EF"),
    (0.75, "#F43F5E"),
    (1.0, "#FF0000"),
]

RECENT_CAPTURES_GRADIENT = [
    (0.0, "#1E293B"),
    (0.33, "#0284C7"),
    (0.66, "#06B6D4"),
    (1.0, "#10B981"),
]


def render_map_legend(mode: str) -> None:
    """Render an on-screen readable color legend matching the active map layer."""
    import streamlit as st

    if mode == "Territory Ownership":
        st.markdown(
            """
            <div style="background: #151E30; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 0.5rem 0.9rem; margin-top: 0.5rem; display: flex; align-items: center; justify-content: space-between; font-size: 0.75rem; color: #94A3B8;">
                <div><strong style="color: #F8FAFC;">Layer Legend:</strong> Deterministic runner colors. Each active runner is assigned an immutable high-contrast HEX palette.</div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="display: inline-block; width: 12px; height: 12px; background: #38BDF8; border-radius: 2px;"></span> <span style="color: #F8FAFC;">Runner A</span>
                    <span style="display: inline-block; width: 12px; height: 12px; background: #F43F5E; border-radius: 2px;"></span> <span style="color: #F8FAFC;">Runner B</span>
                    <span style="display: inline-block; width: 12px; height: 12px; background: #10B981; border-radius: 2px;"></span> <span style="color: #F8FAFC;">Runner C</span>
                    <span style="display: inline-block; width: 12px; height: 12px; background: #64748B; border-radius: 2px;"></span> <span style="color: #94A3B8;">Neutral/Unclaimed</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif mode in ("Activity Heatmap", "Activity Hotspots"):
        st.markdown(
            """
            <div style="background: #151E30; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 0.5rem 0.9rem; margin-top: 0.5rem; font-size: 0.75rem; color: #94A3B8;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <strong style="color: #F8FAFC;">Layer Legend: Activity Heatmap (Visit Density)</strong>
                    <span>Low Traffic → High Intensity Hub</span>
                </div>
                <div style="height: 8px; border-radius: 4px; background: linear-gradient(90deg, #0F172A 0%, #0284C7 20%, #06B6D4 40%, #10B981 60%, #F59E0B 80%, #EF4444 100%);"></div>
                <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: #64748B; margin-top: 0.2rem;">
                    <span>Min Visits</span>
                    <span>Median Density</span>
                    <span>Peak Transits (Max Visits)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif mode == "Contested Zones":
        st.markdown(
            """
            <div style="background: #151E30; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 0.5rem 0.9rem; margin-top: 0.5rem; font-size: 0.75rem; color: #94A3B8;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <strong style="color: #F8FAFC;">Layer Legend: Contested Zones (Hostile Takeover Frequency)</strong>
                    <span>0 Takeovers → Fiercely Contested Battleground</span>
                </div>
                <div style="height: 8px; border-radius: 4px; background: linear-gradient(90deg, #1E293B 0%, #7C3AED 25%, #D946EF 50%, #F43F5E 75%, #FF0000 100%);"></div>
                <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: #64748B; margin-top: 0.2rem;">
                    <span>0 Takeovers (Stable)</span>
                    <span>Moderate Contention</span>
                    <span>Highest Takeovers (Severe Battleground)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif mode == "Recent Captures":
        st.markdown(
            """
            <div style="background: #151E30; border: 1px solid rgba(255,255,255,0.08); border-radius: 6px; padding: 0.5rem 0.9rem; margin-top: 0.5rem; font-size: 0.75rem; color: #94A3B8;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <strong style="color: #F8FAFC;">Layer Legend: Recent Captures (Chronological Recency)</strong>
                    <span>Older Claims → Most Recent Takeovers</span>
                </div>
                <div style="height: 8px; border-radius: 4px; background: linear-gradient(90deg, #1E293B 0%, #0284C7 33%, #06B6D4 66%, #10B981 100%);"></div>
                <div style="display: flex; justify-content: space-between; font-size: 0.7rem; color: #64748B; margin-top: 0.2rem;">
                    <span>Earlier Sessions</span>
                    <span>Mid-Batch Captures</span>
                    <span>Latest Active Captures</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def interpolate_color(val: float, gradient: List[Tuple[float, str]]) -> str:
    """Linearly interpolate HEX color along a segmented gradient [0.0 - 1.0]."""
    v = min(1.0, max(0.0, float(val)))
    for i in range(len(gradient) - 1):
        p0, c0 = gradient[i]
        p1, c1 = gradient[i + 1]
        if p0 <= v <= p1:
            ratio = 0.0 if p1 == p0 else (v - p0) / (p1 - p0)
            r0, g0, b0 = int(c0[1:3], 16), int(c0[3:5], 16), int(c0[5:7], 16)
            r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
            r = int(r0 + ratio * (r1 - r0))
            g = int(g0 + ratio * (g1 - g0))
            b = int(b0 + ratio * (b1 - b0))
            return f"#{r:02x}{g:02x}{b:02x}"
    return gradient[-1][1]


def get_h3_polygon_boundary(cell_id: str) -> Optional[List[List[float]]]:
    """Convert H3 cell ID to a list of [lat, lon] coordinate pairs using H3 4.x.

    Returns:
        List of [lat, lon] coordinates suitable for Folium Polygon.
    """
    if not cell_id or not isinstance(cell_id, str):
        return None
    try:
        # H3 4.x returns tuple of (lat, lon) pairs
        boundary = h3.cell_to_boundary(cell_id)
        return [[lat, lon] for lat, lon in boundary]
    except Exception as exc:
        logger.warning(f"Error converting H3 cell '{cell_id}' to boundary: {exc}")
        return None


def calculate_map_center(h3_cells: List[str]) -> Tuple[float, float]:
    """Calculate centroid of visible H3 cells for dynamic centering."""
    if not h3_cells:
        return DEFAULT_CENTER_LAT, DEFAULT_CENTER_LON
    lats, lons = [], []
    for cell in h3_cells[:100]:
        try:
            lat, lon = h3.cell_to_latlng(cell)
            lats.append(lat)
            lons.append(lon)
        except Exception:
            continue
    if not lats:
        return DEFAULT_CENTER_LAT, DEFAULT_CENTER_LON
    return float(np.mean(lats)), float(np.mean(lons))


def build_zone_tooltip_html(row: pd.Series) -> str:
    """Format rich HTML tooltip/popup for an H3 zone."""
    cell = row.get("h3_cell", "Unknown")
    owner = row.get("current_owner_id", "Unclaimed")
    prev_owner = row.get("previous_owner_id", "None")
    if pd.isna(prev_owner) or str(prev_owner).strip() in ("", "nan", "None"):
        prev_owner = "None (Initial)"

    acq_at = row.get("acquired_at", "N/A")
    if isinstance(acq_at, pd.Timestamp):
        acq_at = acq_at.strftime("%Y-%m-%d %H:%M:%S UTC")

    claims = row.get("total_zone_claims", row.get("total_claims", 0))
    takeovers = row.get("total_zone_takeovers", row.get("takeover_count", 0))
    unique_runners = row.get("unique_zone_runners", row.get("unique_runners", 0))
    revisits = row.get("total_zone_revisits", 0)

    # Ownership changes is initial capture (1) + takeovers
    ownership_changes = (1 if int(claims) > 0 else 0) + int(takeovers)

    return f"""
    <div style="font-family: 'Inter', sans-serif; font-size: 11px; color: #F8FAFC; background: #0F172A; padding: 8px; border-radius: 6px; min-width: 200px;">
        <div style="font-weight: 700; color: #38BDF8; font-size: 12px; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 3px;">
            Zone {cell}
        </div>
        <div><strong>Current Owner:</strong> <span style="color: #22C55E;">{owner}</span></div>
        <div><strong>Previous Owner:</strong> <span style="color: #94A3B8;">{prev_owner}</span></div>
        <div><strong>Last Claim Time:</strong> <span style="color: #CBD5E1;">{acq_at}</span></div>
        <hr style="border: none; border-top: 1px solid rgba(255,255,255,0.08); margin: 4px 0;">
        <div><strong>Total Visits:</strong> {claims}</div>
        <div><strong>Unique Runners:</strong> {unique_runners}</div>
        <div><strong>Takeovers:</strong> {takeovers}</div>
        <div><strong>Revisits:</strong> {revisits}</div>
        <div><strong>Ownership Changes:</strong> {ownership_changes}</div>
    </div>
    """


def render_territory_map(
    zones_df: pd.DataFrame,
    mode: str = "Territory Ownership",
    selected_runner_id: Optional[str] = None,
    highlight_zone_id: Optional[str] = None,
    height: int = 560,
    max_hexagons: int = MAX_HEXAGONS_CAP,
) -> Optional[Dict[str, Any]]:
    """Build and display interactive Folium map for H3 hexagonal territories.

    Modes:
    - 'Territory Ownership': Colored deterministically by current owner.
    - 'Activity Hotspots': Sequential color scale based on total visits or activity.
    - 'Contested Zones': Sequential color scale based on takeover count.

    Args:
        zones_df: DataFrame containing H3 zone records and metrics.
        mode: Map visualization mode.
        selected_runner_id: Optional runner to highlight exclusively.
        highlight_zone_id: Optional specific zone to zoom/highlight.
        height: Map canvas height in pixels.
        max_hexagons: Max hexagon polygons rendered to preserve performance.

    Returns:
        st_folium interaction state dict.
    """
    if zones_df.empty or "h3_cell" not in zones_df.columns:
        return None

    # Enforce polygon limit for responsiveness
    capped_df = zones_df.head(max_hexagons).copy()

    # Determine center and zoom
    center_lat, center_lon = calculate_map_center(capped_df["h3_cell"].tolist())
    zoom = DEFAULT_ZOOM
    if highlight_zone_id and highlight_zone_id in capped_df["h3_cell"].values:
        try:
            center_lat, center_lon = h3.cell_to_latlng(highlight_zone_id)
            zoom = 15
        except Exception:
            pass

    # Initialize Folium Map
    folium_map = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom,
        tiles="OpenStreetMap",
        control_scale=True,
    )

    # Feature Group for H3 Polygons
    fg_hex = folium.FeatureGroup(name=f"H3 Hexagons ({mode})")

    # Min/Max metrics for sequential scales
    if mode in ("Activity Hotspots", "Activity Heatmap"):
        val_col = "total_visits" if "total_visits" in capped_df.columns else "total_zone_claims"
        min_val = float(capped_df[val_col].min()) if not capped_df.empty else 0.0
        max_val = float(capped_df[val_col].max()) if not capped_df.empty else 1.0
    elif mode == "Contested Zones":
        val_col = "takeover_count" if "takeover_count" in capped_df.columns else "total_zone_takeovers"
        min_val = float(capped_df[val_col].min()) if not capped_df.empty else 0.0
        max_val = float(capped_df[val_col].max()) if not capped_df.empty else 1.0
    elif mode == "Recent Captures":
        time_series = pd.to_datetime(capped_df.get("acquired_at", pd.Timestamp.now(tz="UTC")), errors="coerce")
        min_time_epoch = float(time_series.dropna().astype("int64").min() / 1e9) if not time_series.dropna().empty else 0.0
        max_time_epoch = float(time_series.dropna().astype("int64").max() / 1e9) if not time_series.dropna().empty else 1.0

    # Draw each H3 hexagon
    for _, row in capped_df.iterrows():
        cell_id = str(row["h3_cell"])
        boundary = get_h3_polygon_boundary(cell_id)
        if not boundary:
            continue

        owner_id = str(row.get("current_owner_id", ""))
        is_highlighted_zone = highlight_zone_id and (cell_id == highlight_zone_id)
        is_highlighted_runner = selected_runner_id and (owner_id == selected_runner_id)

        # Mode-based color calculation
        if mode == "Territory Ownership":
            base_color = get_runner_color(owner_id)
            if selected_runner_id:
                if is_highlighted_runner:
                    fill_color = base_color
                    border_color = "#FFFFFF"
                    weight = 2.5
                    fill_opacity = 0.85
                else:
                    fill_color = "#334155"
                    border_color = "#1E293B"
                    weight = 0.5
                    fill_opacity = 0.15
            else:
                fill_color = base_color
                border_color = "#FFFFFF" if is_highlighted_zone else base_color
                weight = 2.5 if is_highlighted_zone else 1.2
                fill_opacity = 0.65

        elif mode in ("Activity Hotspots", "Activity Heatmap"):
            raw_v = float(row.get(val_col, 0))
            norm_v = 0.0 if max_val <= min_val else (raw_v - min_val) / (max_val - min_val)
            fill_color = interpolate_color(norm_v, HOTSPOT_GRADIENT)
            border_color = "#FFFFFF" if is_highlighted_zone else fill_color
            weight = 2.5 if is_highlighted_zone else 1.0
            fill_opacity = 0.70

        elif mode == "Recent Captures":
            acq_dt = pd.to_datetime(row.get("acquired_at"), errors="coerce")
            row_epoch = float(acq_dt.value / 1e9) if pd.notna(acq_dt) else min_time_epoch
            norm_v = 0.0 if max_time_epoch <= min_time_epoch else (row_epoch - min_time_epoch) / (max_time_epoch - min_time_epoch)
            fill_color = interpolate_color(norm_v, RECENT_CAPTURES_GRADIENT)
            border_color = "#FFFFFF" if is_highlighted_zone else fill_color
            weight = 2.5 if is_highlighted_zone else 1.2
            fill_opacity = 0.75

        else:  # Contested Zones
            raw_v = float(row.get(val_col, 0))
            norm_v = 0.0 if max_val <= min_val else (raw_v - min_val) / (max_val - min_val)
            fill_color = interpolate_color(norm_v, CONTESTED_GRADIENT)
            border_color = "#FFFFFF" if is_highlighted_zone else fill_color
            weight = 2.5 if is_highlighted_zone else 1.0
            fill_opacity = 0.70

        # Construct Tooltip and Popup
        tooltip_txt = f"Zone: {cell_id} | Owner: {owner_id}"
        popup_html = build_zone_tooltip_html(row)

        poly = folium.Polygon(
            locations=boundary,
            color=border_color,
            weight=weight,
            fill=True,
            fill_color=fill_color,
            fill_opacity=fill_opacity,
            tooltip=folium.Tooltip(tooltip_txt),
            popup=folium.Popup(popup_html, max_width=300),
        )
        poly.add_to(fg_hex)

    fg_hex.add_to(folium_map)
    folium.LayerControl(position="topright").add_to(folium_map)

    # Render via streamlit-folium
    return st_folium(
        folium_map,
        height=height,
        use_container_width=True,
        returned_objects=["last_active_drawing"],
        key="territory_intelligence_map",
    )
