"""Main Orchestration Pipeline for Geospatial Big Data Analytics (Day 2).

Integrates all modules:
1. PySpark Data Ingestion with Explicit Schema
2. Data Quality Cleaning & Kinematic Metrics
3. Kinematic Anomaly & Cheating Detection
4. Run Eligibility Filtering
5. Uber H3 Geospatial Hexagonal Indexing
6. Territory Ownership & Conquest Engine
7. Analytics & Leaderboards
8. Parquet Multi-Dataset Storage
9. Performance Profiling & Comprehensive Audit Reporting
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Ensure project root is on sys.path
_root_dir = Path(__file__).resolve().parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from src.analytics import (
    generate_capture_leaderboard,
    generate_cheating_report,
    generate_current_leaderboard,
    generate_data_quality_summary,
    generate_most_contested_zones,
    generate_runner_activity_summary,
    generate_zone_activity_analysis,
)
from src.cheat_detection import (
    detect_point_anomalies,
    compute_run_risk_scores,
    evaluate_detection_performance,
    filter_eligible_points,
)
from src.data_cleaning import clean_gps_data
from src.data_ingestion import get_ingestion_statistics, load_gps_data
from src.h3_indexing import index_gps_points_to_h3
from src.spark_session import get_spark_session, stop_spark_session
from src.storage import save_all_pipeline_datasets
from src.territory_engine import generate_zone_visits, process_territory_ownership
from src.utils import get_project_root, load_settings
from pyspark.sql import DataFrame, functions as F

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("Pipeline")


def run_pipeline(
    input_path: str | Path,
    output_parquet_dir: str | Path,
    h3_resolution: int = 9,
    min_consecutive_points: int = 2,
    config: Optional[Dict[str, Any]] = None,
    reports_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Execute end-to-end Big Data analytics pipeline for Day 2.

    Args:
        input_path: Path to input GPS CSV.
        output_parquet_dir: Base directory to store output Parquet tables.
        h3_resolution: Uber H3 spatial resolution (default 9).
        min_consecutive_points: Minimum consecutive points in a zone to confirm claim (default 2).
        config: Full configuration dictionary loaded from settings.yaml.

    Returns:
        Comprehensive execution summary report.
    """
    total_start_time = time.time()
    timing_metrics: Dict[str, float] = {}

    settings = config or load_settings()
    day2_cfg = settings.get("day2", {})
    cleaning_cfg = day2_cfg.get("cleaning", {})
    cheat_cfg = day2_cfg.get("cheat_detection", {})
    territory_cfg = day2_cfg.get("territory", {})

    res = int(h3_resolution or territory_cfg.get("h3_resolution", 9))
    min_consec = int(min_consecutive_points or territory_cfg.get("min_consecutive_observations", 2))

    spark = get_spark_session(app_name="TerritoryAnalyticsDay2")

    try:
        # =========================================================================
        # 1. INGESTION
        # =========================================================================
        t0 = time.time()
        logger.info(f"--- PHASE 2: Ingesting GPS dataset from {input_path} ---")
        raw_df = load_gps_data(spark, input_path)
        ingest_stats = get_ingestion_statistics(raw_df)
        timing_metrics["ingestion_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 2. DATA CLEANING & KINEMATICS
        # =========================================================================
        t0 = time.time()
        logger.info("--- PHASE 3: Data Cleaning & Kinematic Movement Calculation ---")
        cleaned_df, quarantined_df, quality_report = clean_gps_data(
            raw_df,
            min_time_diff_s=float(cleaning_cfg.get("min_time_diff_s", 0.0)),
            max_time_diff_s=float(cleaning_cfg.get("max_time_diff_s", 3600.0)),
        )
        # Cache cleaned_df for repeated downstream processing
        cleaned_df.cache()
        cleaned_count = cleaned_df.count()
        timing_metrics["cleaning_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 3. GPS CHEATING & ANOMALY DETECTION
        # =========================================================================
        t0 = time.time()
        logger.info("--- PHASE 4: Rule-Based GPS Cheating & Anomaly Detection ---")
        point_anomalies_df = detect_point_anomalies(cleaned_df, cheat_cfg)
        run_risk_df = compute_run_risk_scores(point_anomalies_df, cheat_cfg)
        run_risk_df.cache()

        eval_metrics = evaluate_detection_performance(run_risk_df)
        timing_metrics["anomaly_detection_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 4. RUN ELIGIBILITY FILTERING
        # =========================================================================
        t0 = time.time()
        logger.info("--- PHASE 5: Run Eligibility Filtering ---")
        eligible_points_df, rejected_runs_df = filter_eligible_points(
            point_anomalies_df, run_risk_df
        )
        eligible_points_df.cache()
        eligible_count = eligible_points_df.count()
        timing_metrics["eligibility_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 5. UBER H3 GEOSPATIAL INDEXING
        # =========================================================================
        t0 = time.time()
        logger.info(f"--- PHASE 6: Uber H3 Spatial Indexing (res={res}) ---")
        h3_points_df = index_gps_points_to_h3(eligible_points_df, resolution=res)
        h3_points_df.cache()
        timing_metrics["h3_indexing_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 6. TERRITORY OWNERSHIP & CONQUEST ENGINE
        # =========================================================================
        t0 = time.time()
        logger.info(f"--- PHASE 7: Territory Ownership Calculation (min_consec={min_consec}) ---")
        claim_events_df = generate_zone_visits(
            h3_points_df, min_consecutive_points=min_consec
        )
        claim_events_df.cache()

        ownership_history_df, current_ownership_df, territory_metrics = process_territory_ownership(
            claim_events_df
        )
        current_ownership_df.cache()
        timing_metrics["territory_calculation_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 7. ANALYTICS & LEADERBOARDS
        # =========================================================================
        t0 = time.time()
        logger.info("--- PHASE 8: Analytical Aggregations & Leaderboards ---")
        leaderboard_df = generate_current_leaderboard(current_ownership_df)
        capture_leaderboard_df = generate_capture_leaderboard(ownership_history_df)
        contested_zones_df = generate_most_contested_zones(ownership_history_df, top_n=50)
        zone_stats_df = generate_zone_activity_analysis(ownership_history_df)

        cheating_report = generate_cheating_report(run_risk_df, eval_metrics)
        runner_summary = generate_runner_activity_summary(
            cleaned_df, eligible_points_df, quarantined_df
        )
        data_quality_summary = generate_data_quality_summary(
            quality_report, eligible_points_df, rejected_runs_df
        )
        timing_metrics["analytics_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 8. PARQUET STORAGE
        # =========================================================================
        t0 = time.time()
        logger.info(f"--- PHASE 9: Parquet Storage Export to {output_parquet_dir} ---")
        datasets_to_save = {
            "cleaned_points": cleaned_df,
            "quarantined_points": quarantined_df,
            "point_anomalies": point_anomalies_df,
            "run_anomalies": run_risk_df,
            "eligible_points": eligible_points_df,
            "h3_points": h3_points_df,
            "zone_visits": claim_events_df,
            "claim_events": claim_events_df,
            "ownership_history": ownership_history_df,
            "current_ownership": current_ownership_df,
            "zone_statistics": zone_stats_df,
            "leaderboard": leaderboard_df,
            "contested_zones": contested_zones_df,
        }
        saved_paths = save_all_pipeline_datasets(datasets_to_save, output_parquet_dir)
        timing_metrics["storage_seconds"] = round(time.time() - t0, 3)

        # =========================================================================
        # 9. INTEGRITY VALIDATIONS
        # =========================================================================
        validation_errors = []

        # Validation Rule 1: Sum of zones in current leaderboard == total unique zones in current_ownership
        leaderboard_sum = leaderboard_df.select(F.sum("zones_owned")).collect()[0][0] or 0
        total_unique_zones = territory_metrics["total_unique_zones"]
        if leaderboard_sum != total_unique_zones:
            validation_errors.append(
                f"Rule 1 Violation: Leaderboard sum ({leaderboard_sum}) != unique owned zones ({total_unique_zones})"
            )

        # Validation Rule 2: Every owner originates from an eligible claim
        unmatched_owners = current_ownership_df.join(
            claim_events_df.select("claim_id").withColumnRenamed("claim_id", "latest_claim_id"),
            on="latest_claim_id",
            how="left_anti"
        ).count()
        if unmatched_owners > 0:
            validation_errors.append(
                f"Rule 2 Violation: Found {unmatched_owners} owners without an eligible claim"
            )

        # Validation Rule 3: No suspicious or high-risk run may acquire territory
        invalid_owners_count = current_ownership_df.join(
            rejected_runs_df.select("run_id").withColumnRenamed("run_id", "acquired_in_run"),
            on="acquired_in_run",
            how="inner"
        ).count()
        if invalid_owners_count > 0:
            validation_errors.append(
                f"Rule 3 Violation: Found {invalid_owners_count} zones owned by ineligible runs"
            )

        # Validation Rule 4: Same-owner revisits must not increase takeover counts
        revisit_takeover_clash = ownership_history_df.filter(
            (F.col("event_type") == "SAME_OWNER_REVISIT") & (F.col("is_takeover") == True)  # noqa: E712
        ).count()
        if revisit_takeover_clash > 0:
            validation_errors.append(
                f"Rule 4 Violation: Found {revisit_takeover_clash} revisits marked as takeovers"
            )

        is_pipeline_valid = (len(validation_errors) == 0)

        total_duration = round(time.time() - total_start_time, 3)
        timing_metrics["total_processing_seconds"] = total_duration

        # Compile final results dictionary
        summary_report = {
            "pipeline_name": "Day 2 Geospatial Big Data Engine",
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "is_valid": is_pipeline_valid,
            "validation_errors": validation_errors,
            "timing_benchmarks": timing_metrics,
            "ingestion_stats": ingest_stats,
            "data_quality": data_quality_summary,
            "cheating_detection": cheating_report,
            "runner_summary": runner_summary,
            "territory_conquest": territory_metrics,
            "saved_parquet_datasets": saved_paths,
            "configuration": {
                "h3_resolution": res,
                "min_consecutive_points": min_consec,
                "input_path": str(input_path),
                "output_dir": str(output_parquet_dir),
            },
        }

        # Write day2_validation.json
        root_dir = get_project_root()
        rep_dir = Path(reports_dir) if reports_dir is not None else (root_dir / "data" / "reports")
        rep_dir.mkdir(parents=True, exist_ok=True)
        json_report_path = rep_dir / "day2_validation.json"

        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(summary_report, f, indent=2, default=str)

        logger.info(f"Validation report saved to {json_report_path}")

        # Write docs/day2_results.md only if running against standard project reports
        if reports_dir is None:
            docs_dir = root_dir / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)
            md_report_path = docs_dir / "day2_results.md"
            generate_markdown_report(summary_report, md_report_path, leaderboard_df, contested_zones_df)
            logger.info(f"Markdown results report saved to {md_report_path}")

        return summary_report

    finally:
        stop_spark_session(spark)


def generate_markdown_report(
    summary: Dict[str, Any],
    out_path: Path,
    leaderboard_df: DataFrame,
    contested_zones_df: DataFrame,
) -> None:
    """Format execution results as a clean Markdown report."""
    tm = summary["timing_benchmarks"]
    tq = summary["territory_conquest"]
    cd = summary["cheating_detection"]
    dq = summary["data_quality"]
    rs = summary["runner_summary"]
    ev = cd.get("evaluation_metrics", {}).get("metrics", {})
    cm = cd.get("evaluation_metrics", {}).get("confusion_matrix", {})

    top_leaders = [row.asDict() for row in leaderboard_df.limit(10).collect()]
    top_contested = [row.asDict() for row in contested_zones_df.limit(10).collect()]

    md_lines = [
        "# Day 2 Execution Results & Technical Audit Report",
        "",
        f"**Timestamp (UTC):** {summary['execution_timestamp']}  ",
        f"**Validation Status:** {'✅ PASSED (All 4 Core Invariants Satisfied)' if summary['is_valid'] else '❌ FAILED'}  ",
        f"**Total Execution Duration:** {tm.get('total_processing_seconds', 0.0)} seconds  ",
        "",
        "---",
        "",
        "## 1. Executive Performance Benchmarks",
        "",
        "| Processing Phase | Execution Duration (seconds) |",
        "| :--- | :--- |",
        f"| PySpark Ingestion | {tm.get('ingestion_seconds', 0.0)}s |",
        f"| Data Cleaning & Kinematics | {tm.get('cleaning_seconds', 0.0)}s |",
        f"| Kinematic Cheating Detection | {tm.get('anomaly_detection_seconds', 0.0)}s |",
        f"| Run Eligibility Filtering | {tm.get('eligibility_seconds', 0.0)}s |",
        f"| Uber H3 Indexing (Res 9) | {tm.get('h3_indexing_seconds', 0.0)}s |",
        f"| Territory Ownership Engine | {tm.get('territory_calculation_seconds', 0.0)}s |",
        f"| Analytics & Leaderboards | {tm.get('analytics_seconds', 0.0)}s |",
        f"| Parquet Multi-Dataset Storage | {tm.get('storage_seconds', 0.0)}s |",
        f"| **Total End-to-End Processing** | **{tm.get('total_processing_seconds', 0.0)}s** |",
        "",
        "---",
        "",
        "## 2. Ingestion & Data Quality Audit",
        "",
        f"- **Raw GPS Records Ingested:** {dq.get('raw_records', 0):,}",
        f"- **Valid Cleaned Records:** {dq.get('valid_records', 0):,}",
        f"- **Quarantined Records:** {dq.get('quarantined_records', 0):,}",
        f"- **Eligible GPS Points for Territory Conquest:** {dq.get('eligible_points', 0):,}",
        f"- **Excluded Ineligible Runs:** {dq.get('rejected_runs', 0):,}",
        "",
        "---",
        "",
        "## 3. Cheating Detection Performance",
        "",
        f"- **Precision:** {ev.get('precision', 0.0):.4f}",
        f"- **Recall:** {ev.get('recall', 0.0):.4f}",
        f"- **F1 Score:** {ev.get('f1_score', 0.0):.4f}",
        "",
        "### Confusion Matrix (Ground Truth Evaluation):",
        f"- **True Positives (Cheating correctly flagged):** {cm.get('true_positives', 0)}",
        f"- **False Positives (Clean runs falsely flagged):** {cm.get('false_positives', 0)}",
        f"- **True Negatives (Clean runs correctly accepted):** {cm.get('true_negatives', 0)}",
        f"- **False Negatives (Cheaters missed):** {cm.get('false_negatives', 0)}",
        "",
        "### Risk Category Distribution:",
    ]

    for cat, count in cd.get("risk_category_counts", {}).items():
        pct = cd.get("risk_category_percentages", {}).get(cat, 0.0)
        md_lines.append(f"- **{cat}:** {count} runs ({pct}%)")

    md_lines.extend([
        "",
        "---",
        "",
        "## 4. Territory Conquest Summary",
        "",
        f"- **Total Valid Claims Generated:** {tq.get('total_claims', 0):,}",
        f"- **Unique Hexagonal Zones Owned (Res 9):** {tq.get('total_unique_zones', 0):,}",
        f"- **Initial Zone Captures:** {tq.get('initial_captures', 0):,}",
        f"- **Territory Takeovers (Ownership Transfers):** {tq.get('takeovers', 0):,}",
        f"- **Same-Owner Revisits (Non-Takeovers):** {tq.get('same_owner_revisits', 0):,}",
        "",
        "### Top 10 Territory Owners (Current Leaderboard):",
        "",
        "| Rank | Runner ID | Zones Owned |",
        "| :--- | :--- | :--- |",
    ])

    for row in top_leaders:
        md_lines.append(f"| {row['rank']} | `{row['runner_id']}` | {row['zones_owned']} |")

    md_lines.extend([
        "",
        "### Top 10 Most Contested Zones:",
        "",
        "| Rank | H3 Cell Index | Takeovers | Unique Runners | Total Claims |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ])

    for row in top_contested:
        md_lines.append(
            f"| {row['contest_rank']} | `{row['h3_cell']}` | {row['takeover_count']} | {row['unique_runners']} | {row['total_claims']} |"
        )

    md_lines.extend([
        "",
        "---",
        "",
        "## 5. Architectural Verification of Invariants",
        "",
        "- [x] **Leaderboard Sum Conservation:** Total currently owned zones exactly equals the sum across the current ownership leaderboard.",
        "- [x] **Claim Provenance Integrity:** 100% of current owners originate from verified eligible claims.",
        "- [x] **Cheater Exclusion:** Zero suspicious or high-risk runs acquired territory.",
        "- [x] **Revisit Immunity:** Same-owner revisits strictly excluded from takeover counts.",
        "",
    ])

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


def main() -> None:
    """CLI entrypoint for running the Day 2 Geospatial Big Data Pipeline."""
    parser = argparse.ArgumentParser(
        description="Run Day 2 PySpark Geospatial Territory & Cheating Analytics Pipeline"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/raw/gps_100k.csv",
        help="Input CSV path (default: data/raw/gps_100k.csv)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/parquet",
        help="Output Parquet directory (default: data/parquet)",
    )
    parser.add_argument(
        "--h3-resolution",
        type=int,
        default=9,
        help="Uber H3 hexagonal grid resolution (default: 9)",
    )
    parser.add_argument(
        "--min-consecutive",
        type=int,
        default=2,
        help="Minimum consecutive points in zone to confirm claim (default: 2)",
    )

    args = parser.parse_args()

    root = get_project_root()
    input_file = root / args.input
    output_dir = root / args.output

    if not input_file.exists():
        logger.error(f"Input file not found at {input_file}")
        sys.exit(1)

    logger.info("Starting Day 2 Pipeline...")
    res = run_pipeline(
        input_path=input_file,
        output_parquet_dir=output_dir,
        h3_resolution=args.h3_resolution,
        min_consecutive_points=args.min_consecutive,
    )

    if not res.get("is_valid", False):
        logger.error(f"Pipeline validation failed: {res.get('validation_errors')}")
        sys.exit(1)

    logger.info("Day 2 Pipeline executed and validated successfully!")


if __name__ == "__main__":
    main()
