"""Synthetic GPS Track Generator for Geospatial Big Data Analytics.

Generates realistic, reproducible, sequential GPS tracks for simulated runners
in Chicago with 6 behavioral scenarios including fraud and GPS anomalies.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.geo_utils import (
    calculate_bearing,
    destination_point,
    haversine_distance_m,
)
from src.utils import format_iso_z, get_project_root, load_settings

# CSV Columns in exact required order
CSV_COLUMNS = [
    "run_id",
    "runner_id",
    "timestamp",
    "latitude",
    "longitude",
    "heart_rate",
    "cadence",
    "elevation_m",
    "distance_m",
    "device_type",
    "activity_type",
    "scenario_type",
]

# Metadata CSV Columns
METADATA_COLUMNS = [
    "run_id",
    "runner_id",
    "scenario_type",
    "start_time",
    "end_time",
    "point_count",
    "seed",
]

# Realistic Chicago running hubs within ~5km of Loop center (41.8781, -87.6298)
CHICAGO_HUBS = [
    {"name": "Millennium Park", "lat": 41.8826, "lon": -87.6226},
    {"name": "Grant Park Fountain", "lat": 41.8758, "lon": -87.6189},
    {"name": "Lakefront Trail North", "lat": 41.8970, "lon": -87.6150},
    {"name": "Lakefront Trail South", "lat": 41.8650, "lon": -87.6140},
    {"name": "Chicago Riverwalk", "lat": 41.8870, "lon": -87.6280},
    {"name": "Loop Financial", "lat": 41.8790, "lon": -87.6320},
    {"name": "Museum Campus", "lat": 41.8660, "lon": -87.6170},
    {"name": "Near North / Mag Mile", "lat": 41.8940, "lon": -87.6240},
]

DEVICE_TYPES = [
    "Garmin Forerunner 965",
    "Apple Watch Ultra 2",
    "Coros Pace 3",
    "Polar Vantage V3",
    "Suunto Race",
]

SCENARIO_PROPORTIONS = {
    "normal_run": 0.55,
    "fast_run": 0.10,
    "walking": 0.10,
    "driving": 0.10,
    "gps_spoofing": 0.10,
    "gps_noise": 0.05,
}


@dataclass
class RunProfile:
    """Configuration profile for a single simulated run."""
    run_id: str
    runner_id: str
    scenario_type: str
    device_type: str
    point_count: int
    start_time: datetime
    start_lat: float
    start_lon: float


def allocate_run_point_counts(total_records: int, num_runs: int, rng: random.Random) -> List[int]:
    """Distribute exactly total_records across num_runs, ensuring each run has >= 3 points."""
    if num_runs * 3 > total_records:
        raise ValueError(
            f"Cannot allocate {total_records} records across {num_runs} runs with minimum 3 points per run."
        )

    # Base allocation of 3 points per run
    counts = [3] * num_runs
    remaining = total_records - (num_runs * 3)

    if remaining > 0:
        # Generate random weights for each run to create variable track lengths
        weights = [rng.uniform(0.5, 2.5) for _ in range(num_runs)]
        total_weight = sum(weights)
        allocations = [int(remaining * (w / total_weight)) for w in weights]

        # Distribute the allocated points
        for i in range(num_runs):
            counts[i] += allocations[i]

        # Fix rounding remainder to match total_records exactly
        diff = total_records - sum(counts)
        for i in range(abs(diff)):
            idx = i % num_runs
            counts[idx] += 1 if diff > 0 else -1

    assert sum(counts) == total_records, f"Allocated {sum(counts)} != expected {total_records}"
    assert all(c >= 3 for c in counts), "All runs must have at least 3 points"
    return counts


def assign_scenarios(num_runs: int, rng: random.Random) -> List[str]:
    """Assign scenario categories ensuring all 6 scenarios are represented when num_runs >= 6."""
    all_scenarios = list(SCENARIO_PROPORTIONS.keys())
    weights = [SCENARIO_PROPORTIONS[s] for s in all_scenarios]

    if num_runs < len(all_scenarios):
        # Sample directly according to weights if num_runs is tiny
        return rng.choices(all_scenarios, weights=weights, k=num_runs)

    # Guarantee at least 1 of each scenario
    assigned = list(all_scenarios)
    remaining_count = num_runs - len(assigned)

    if remaining_count > 0:
        extra = rng.choices(all_scenarios, weights=weights, k=remaining_count)
        assigned.extend(extra)

    rng.shuffle(assigned)
    return assigned


def generate_single_run_points(
    profile: RunProfile,
    center_lat: float,
    center_lon: float,
    max_radius_m: float,
    rng: random.Random,
) -> List[Dict[str, str | float | int]]:
    """Generate sequential GPS points for a single run profile."""
    scenario = profile.scenario_type
    points: List[Dict[str, str | float | int]] = []

    current_lat = profile.start_lat
    current_lon = profile.start_lon
    current_time = profile.start_time
    bearing = rng.uniform(0.0, 360.0)
    elevation_m = 181.0 + rng.uniform(-2.0, 4.0)
    cumulative_distance_m = 0.0

    # Determine spoofing / noise trigger indices
    spoof_start_idx = -1
    spoof_duration = 0
    noise_indices = set()

    if scenario == "gps_spoofing" and profile.point_count >= 5:
        # A jump occurs in the middle portion of the run
        spoof_start_idx = rng.randint(2, max(2, profile.point_count - 3))
        spoof_duration = rng.randint(1, min(3, profile.point_count - spoof_start_idx - 1))
    elif scenario == "gps_noise":
        # 1-3 isolated noise spikes
        num_spikes = min(profile.point_count // 5, rng.randint(1, 3))
        if num_spikes > 0:
            noise_indices = set(rng.sample(range(1, profile.point_count - 1), num_spikes))

    for i in range(profile.point_count):
        if i == 0:
            # First point
            reported_lat = current_lat
            reported_lon = current_lon
        else:
            # Time delta between 3 and 10 seconds
            dt_s = rng.randint(3, 10)
            current_time += timedelta(seconds=dt_s)

            # Determine speed (km/h) based on scenario
            if scenario == "normal_run":
                speed_kmh = rng.uniform(5.0, 12.0)
            elif scenario == "fast_run":
                speed_kmh = rng.uniform(10.0, 20.0)
            elif scenario == "walking":
                speed_kmh = rng.uniform(3.0, 6.0)
            elif scenario == "driving":
                speed_kmh = rng.uniform(30.0, 80.0)
            elif scenario in ("gps_spoofing", "gps_noise"):
                speed_kmh = rng.uniform(5.0, 12.0)
            else:
                speed_kmh = rng.uniform(5.0, 12.0)

            speed_ms = speed_kmh / 3.6
            physical_step_m = speed_ms * dt_s
            cumulative_distance_m += physical_step_m

            # Steering and direction
            dist_from_center = haversine_distance_m(current_lat, current_lon, center_lat, center_lon)
            if dist_from_center > max_radius_m * 0.85:
                # Turn back toward center
                center_bearing = calculate_bearing(current_lat, current_lon, center_lat, center_lon)
                bearing = (0.7 * bearing + 0.3 * center_bearing) % 360.0
            else:
                bearing = (bearing + rng.gauss(0.0, 8.0)) % 360.0

            # Advance physical position
            current_lat, current_lon = destination_point(current_lat, current_lon, physical_step_m, bearing)
            elevation_m = max(175.0, min(195.0, elevation_m + rng.gauss(0.0, 0.2)))

            # Handle reported coordinates (anomalies vs true track)
            reported_lat = current_lat
            reported_lon = current_lon

            if scenario == "gps_spoofing" and spoof_start_idx <= i < (spoof_start_idx + spoof_duration):
                # Impossible sudden geographic jump (teleportation outside Chicago study region)
                # Example: jump ~40km North/Northwest
                reported_lat = current_lat + 0.35 + rng.uniform(-0.02, 0.02)
                reported_lon = current_lon - 0.25 + rng.uniform(-0.02, 0.02)
                # Physical distance_m does NOT increase for the jump (cumulative_distance_m stays physical)
            elif scenario == "gps_noise" and i in noise_indices:
                # Intermittent isolated GPS error (jitter 100-300m offset)
                jitter_bearing = rng.uniform(0.0, 360.0)
                jitter_dist = rng.uniform(80.0, 250.0)
                reported_lat, reported_lon = destination_point(current_lat, current_lon, jitter_dist, jitter_bearing)

        # Heart rate and cadence simulation
        if scenario == "driving":
            # In a vehicle claiming to run: low heart rate and minimal cadence
            heart_rate = int(rng.gauss(75.0, 5.0))
            cadence = int(max(0, rng.gauss(15.0, 10.0)))
        elif scenario == "walking":
            heart_rate = int(rng.gauss(100.0, 7.0))
            cadence = int(rng.gauss(110.0, 6.0))
        elif scenario == "fast_run":
            heart_rate = int(rng.gauss(172.0, 6.0))
            cadence = int(rng.gauss(180.0, 5.0))
        else:  # normal_run, gps_spoofing, gps_noise
            heart_rate = int(rng.gauss(148.0, 8.0))
            cadence = int(rng.gauss(165.0, 6.0))

        # Clamp physiologic values
        heart_rate = max(50, min(210, heart_rate))
        cadence = max(0, min(220, cadence))

        row: Dict[str, str | float | int] = {
            "run_id": profile.run_id,
            "runner_id": profile.runner_id,
            "timestamp": format_iso_z(current_time),
            "latitude": round(reported_lat, 6),
            "longitude": round(reported_lon, 6),
            "heart_rate": heart_rate,
            "cadence": cadence,
            "elevation_m": round(elevation_m, 1),
            "distance_m": round(cumulative_distance_m, 1),
            "device_type": profile.device_type,
            "activity_type": "running",  # Always 'running' to simulate activity fraud
            "scenario_type": scenario,
        }
        points.append(row)

    return points


def generate_dataset(
    records: int = 1000,
    runners: int = 25,
    seed: int = 42,
    output_path: str | Path = "data/raw/gps_demo.csv",
    metadata_path: Optional[str | Path] = None,
    buffer_size: int = 5000,
) -> Dict[str, Any]:
    """Generate a synthetic GPS dataset streaming directly to disk with bounded memory.

    Args:
        records: Total number of GPS points to generate.
        runners: Number of distinct runners.
        seed: Random seed for deterministic reproducibility.
        output_path: Path to target CSV file.
        metadata_path: Optional path to metadata CSV file.
        buffer_size: Maximum row buffer size before flushing to disk.

    Returns:
        Summary statistics dictionary.
    """
    rng = random.Random(seed)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Determine metadata output path
    if metadata_path is None:
        # Default: write to matching stem runs_metadata_<stem>.csv and data/raw/runs_metadata.csv
        stem = output_file.stem
        metadata_file = output_file.parent / f"runs_metadata_{stem}.csv"
    else:
        metadata_file = Path(metadata_path)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)

    # Load spatial bounds
    center_lat = 41.8781
    center_lon = -87.6298
    radius_m = 5000.0

    # Determine number of runs (aim for realistic ~40-100 points per run, with at least 6 runs)
    if records <= 2000:
        num_runs = max(6, min(runners, records // 25))
    else:
        num_runs = max(6, min(records // 50, runners * 5))

    point_counts = allocate_run_point_counts(records, num_runs, rng)
    scenario_assignments = assign_scenarios(num_runs, rng)

    # Assign runners their consistent device
    runner_devices = {
        f"runner_{i:03d}": rng.choice(DEVICE_TYPES)
        for i in range(1, runners + 1)
    }

    # Base reference date for runs (2026-10-26 with staggered starting times)
    base_time = datetime(2026, 10, 26, 6, 0, 0, tzinfo=timezone.utc)

    # Prepare run profiles
    run_profiles: List[RunProfile] = []
    for k in range(num_runs):
        run_id = f"run_{k + 1:04d}"
        runner_id = f"runner_{(k % runners) + 1:03d}"
        scenario = scenario_assignments[k]
        device = runner_devices[runner_id]
        points_in_run = point_counts[k]

        # Stagger start times: overlapping runs across morning/afternoon
        start_offset_s = rng.randint(0, 14400)  # within 4 hours
        start_time = base_time + timedelta(seconds=start_offset_s)

        # Pick a starting hub with small jitter (~50-150m)
        hub = rng.choice(CHICAGO_HUBS)
        start_lat, start_lon = destination_point(
            hub["lat"], hub["lon"], rng.uniform(20.0, 150.0), rng.uniform(0.0, 360.0)
        )

        run_profiles.append(
            RunProfile(
                run_id=run_id,
                runner_id=runner_id,
                scenario_type=scenario,
                device_type=device,
                point_count=points_in_run,
                start_time=start_time,
                start_lat=start_lat,
                start_lon=start_lon,
            )
        )

    # Generate points and stream directly to disk
    total_written = 0
    scenario_counts: Dict[str, int] = {s: 0 for s in SCENARIO_PROPORTIONS.keys()}
    scenario_run_counts: Dict[str, int] = {s: 0 for s in SCENARIO_PROPORTIONS.keys()}
    metadata_rows: List[Dict[str, Any]] = []

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_COLUMNS)
        writer.writeheader()

        row_buffer: List[Dict[str, Any]] = []

        for profile in run_profiles:
            run_points = generate_single_run_points(
                profile,
                center_lat=center_lat,
                center_lon=center_lon,
                max_radius_m=radius_m,
                rng=rng,
            )

            scenario_run_counts[profile.scenario_type] += 1
            scenario_counts[profile.scenario_type] += len(run_points)
            total_written += len(run_points)

            metadata_rows.append({
                "run_id": profile.run_id,
                "runner_id": profile.runner_id,
                "scenario_type": profile.scenario_type,
                "start_time": run_points[0]["timestamp"],
                "end_time": run_points[-1]["timestamp"],
                "point_count": len(run_points),
                "seed": seed,
            })

            row_buffer.extend(run_points)
            if len(row_buffer) >= buffer_size:
                writer.writerows(row_buffer)
                row_buffer.clear()

        if row_buffer:
            writer.writerows(row_buffer)
            row_buffer.clear()

    # Write metadata CSV
    with open(metadata_file, "w", newline="", encoding="utf-8") as metafile:
        meta_writer = csv.DictWriter(metafile, fieldnames=METADATA_COLUMNS)
        meta_writer.writeheader()
        meta_writer.writerows(metadata_rows)

    # Also write/update standard data/raw/runs_metadata.csv if not identical
    standard_meta = output_file.parent / "runs_metadata.csv"
    if standard_meta.resolve() != metadata_file.resolve():
        with open(standard_meta, "w", newline="", encoding="utf-8") as stdfile:
            std_writer = csv.DictWriter(stdfile, fieldnames=METADATA_COLUMNS)
            std_writer.writeheader()
            std_writer.writerows(metadata_rows)

    summary = {
        "output_file": str(output_file),
        "metadata_file": str(metadata_file),
        "standard_metadata_file": str(standard_meta),
        "total_records": total_written,
        "total_runs": num_runs,
        "total_runners": len(set(p.runner_id for p in run_profiles)),
        "seed": seed,
        "file_size_bytes": output_file.stat().st_size,
        "scenario_points": scenario_counts,
        "scenario_runs": scenario_run_counts,
    }

    return summary


def print_summary(summary: Dict[str, Any]) -> None:
    """Print a clean CLI summary of the generated dataset."""
    print("=" * 60)
    print("  GEOSPATIAL BIG DATASET GENERATION SUMMARY")
    print("=" * 60)
    print(f"Output File:       {summary['output_file']}")
    print(f"Metadata File:     {summary['metadata_file']}")
    print(f"Total Points:      {summary['total_records']:,}")
    print(f"Total Runs:        {summary['total_runs']}")
    print(f"Total Runners:     {summary['total_runners']}")
    print(f"Random Seed:       {summary['seed']}")
    print(f"File Size:         {summary['file_size_bytes'] / 1024:.2f} KB")
    print("-" * 60)
    print(f"{'Scenario':<16} {'Runs':<8} {'Run %':<10} {'Points':<10} {'Points %'}")
    print("-" * 60)
    total_runs = summary["total_runs"]
    total_pts = summary["total_records"]
    for sc, pts in summary["scenario_points"].items():
        runs = summary["scenario_runs"][sc]
        run_pct = (runs / total_runs) * 100.0 if total_runs else 0.0
        pt_pct = (pts / total_pts) * 100.0 if total_pts else 0.0
        print(f"{sc:<16} {runs:<8} {run_pct:<10.1f} {pts:<10} {pt_pct:.1f}%")
    print("=" * 60)


def main() -> None:
    """CLI entrypoint for data generation."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic geospatial GPS dataset for territory control analytics."
    )
    parser.add_argument(
        "--records",
        type=int,
        default=1000,
        help="Total number of GPS records to generate (default: 1000).",
    )
    parser.add_argument(
        "--runners",
        type=int,
        default=25,
        help="Number of simulated runners (default: 25).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible generation (default: 42).",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/raw/gps_demo.csv",
        help="Path for output GPS points CSV (default: data/raw/gps_demo.csv).",
    )
    parser.add_argument(
        "--metadata",
        type=str,
        default=None,
        help="Optional path for run metadata CSV.",
    )

    args = parser.parse_args()
    summary = generate_dataset(
        records=args.records,
        runners=args.runners,
        seed=args.seed,
        output_path=args.output,
        metadata_path=args.metadata,
    )
    print_summary(summary)


if __name__ == "__main__":
    main()
