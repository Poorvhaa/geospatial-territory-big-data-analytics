"""Dashboard services package for Territory Intelligence BI Platform."""

from dashboard.services.data_loader import (
    load_all_datasets,
    load_claim_events,
    load_contested_zones,
    load_current_ownership,
    load_leaderboard,
    load_ownership_history,
    load_pipeline_report,
    load_run_anomalies,
    load_zone_statistics,
)
from dashboard.services.exports import generate_csv_download
from dashboard.services.filters import (
    filter_by_metric,
    filter_by_risk_category,
    filter_by_runner,
    filter_by_time_range,
    filter_by_top_n,
    filter_by_zone,
)
from dashboard.services.metrics import (
    calculate_combined_leaderboard,
    calculate_hotspot_scores,
    calculate_kpis,
    get_runner_color,
)

__all__ = [
    "load_all_datasets",
    "load_pipeline_report",
    "load_current_ownership",
    "load_ownership_history",
    "load_zone_statistics",
    "load_contested_zones",
    "load_leaderboard",
    "load_run_anomalies",
    "load_claim_events",
    "calculate_kpis",
    "calculate_combined_leaderboard",
    "calculate_hotspot_scores",
    "get_runner_color",
    "filter_by_runner",
    "filter_by_time_range",
    "filter_by_risk_category",
    "filter_by_zone",
    "filter_by_metric",
    "filter_by_top_n",
    "generate_csv_download",
]
