# Live Project Demonstration Script
## Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data
**Duration:** 5–7 Minutes  
**Audience:** Technical Evaluators, Big Data Architects, and Academic Defense Committee

---

## Pre-Demonstration Setup & One-Click Preparation
Before starting the presentation, you can prepare the entire environment with a single automated command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\prepare_demo.ps1
```
*(Executes 8 automated checks: venv validation, dependencies, Parquet datasets, SQLite state reset, demo track generation, data consistency verification, and launch readiness confirmation).*

Alternatively, to start the application immediately:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_project.ps1
```

To run the complete automated test suite (all 89 tests):
```powershell
python -m pytest
```

---

## Demonstration Flow (Step-by-Step)

### Step 1: Introduction & Problem Context (1 Minute)
**Presenter Speech:**
> "Welcome. Today we present our capstone big data platform: **Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data**.
> Modern fitness apps like Strava and Ingress gamify outdoor movement by letting athletes conquer geographical zones.
> However, building this at city scale presents three critical big data challenges:
> 1. Noisy GPS telemetry and sensor drift.
> 2. Cheating—such as vehicle driving and GPS coordinate spoofing.
> 3. Computational geometric bottlenecks when calculating overlapping boundaries for millions of points.
> We solved these using **Apache PySpark**, **Uber H3 hexagonal spatial indexing**, **columnar Parquet storage**, and an **incremental real-time simulation engine**."

---

### Step 2: Synthetic Telemetry Generation (45 Seconds)
**Presenter Action:**
Run the data generator to display realistic Chicago Loop trajectory generation:
```powershell
python -m src.data_generator --records 5000 --runners 10 --seed 42 --output data/raw/gps_demo.csv
```

**Presenter Speech:**
> "We implemented a seeded synthetic generator that models 6 behavioral scenarios: normal runs, fast runs, walking, motor vehicles, GPS spoofing, and multipath noise around 7 Chicago hubs like Millennium Park and Lakefront Trail. Monotonically increasing timestamps and physical distance progression are strictly guaranteed."

---

### Step 3: Spark Distributed Processing & Anomaly Detection (1 Minute)
**Presenter Action:**
Explain the distributed pipeline execution:
```powershell
python -m src.pipeline --input data/raw/gps_100k.csv --output-parquet data/parquet
```

**Presenter Speech:**
> "Our PySpark pipeline ingests the raw GPS dataset with explicit `StructType` schemas.
> Using distributed PySpark Window functions, we calculate Haversine distances, instantaneous speeds, and accelerations without collecting data to driver memory.
> Our rule-based cheat detection engine identifies:
> - Impossible speeds exceeding 25 km/h.
> - Teleportation jumps of 300+ meters.
> - Driving patterns combining high vehicle speed with near-zero cadence.
> - Multipath noise spikes using chord distance return analysis.
> Out of 1,250 runs in our 100K dataset, 307 fraudulent runs were quarantined. Only validated NORMAL runs are eligible for territory conquest."

---

### Step 4: Launching the BI Production Dashboard (1 Minute)
**Presenter Action:**
Launch the Streamlit analytics platform:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_project.ps1
```
*(The dashboard opens automatically at `http://localhost:8501`)*.

**Presenter Speech:**
> "Let's explore the Territory Intelligence BI Dashboard:
> - **Overview Home Page:** Displays 8 real KPI metrics—100,000 GPS Records, 250 Runners, 943 Valid Running Activities, 308 Current Territory Zones, 4,729 Ownership Takeovers, 233 Contested Zones, 307 Suspicious Activities, and Synchronized Status. It also features our automated Analytical Insights briefing, territory breakdown, top 5 runners, and risk donuts.
> - **Territory Map:** Displays Uber H3 Resolution 9 hexagons covering Chicago across 4 distinct layers: Territory Ownership, Activity Heatmap, Contested Zones, and Recent Captures, complete with on-screen color legends and configurable polygon display limits.
> - **Leaderboard:** Ranks athletes with verified reconciliation: sum of zones owned (308) matches current territory records.
> - **Hotspot Analytics:** Displays composite scores ($0.40T + 0.35U + 0.25V$), dynamic natural language interpretations, and an interactive Zone Drill-Down panel.
> - **Cheat Detection:** Features an individual run explainability deep-dive with confusion matrix evaluation (Precision 80.13%, Recall 100%, F1 0.8897)."

---

### Step 5: Live Simulation & Real-Time Territory Conquest (2 Minutes)
**Presenter Action:**
1. Navigate in the sidebar to: **⚡ Live Simulation**.
2. Point out the initial state: Engine status is **STOPPED** or shows committed progress.
3. Click **🔄 RESTART** to reset the state store to Event 0.
4. Select **5x Playback Speed**.
5. Click **▶️ START**.
6. Observe:
   - Progress bar begins advancing.
   - GPS Points Replayed and Valid Territory Claims count upward in real time.
   - On the Live Hex Map, newly captured zones flash with an **emerald green outline**, and takeovers flash with a **fiery red outline**.
   - On the right, the **🏆 Live Leaderboard** dynamically re-ranks runners.
   - The **⚡ Live Feed** displays instantaneous conquest alerts (e.g., *'Runner runner_03 conquered zone 892664c1b... from runner_11!'*).
7. Click **⏸️ PAUSE**:
   - Show that event time freezes without losing committed state.
8. Click **⏯️ RESUME**:
   - Playback continues seamlessly without re-processing already committed batches.

**Presenter Speech:**
> "Here on the Live Simulation page, our background `ReplayEngine` slices time-ordered GPS events into 5-second micro-batches.
> An SQLite transactional store commits claims, ownership updates, and checkpoints atomically with zero duplicate processing.
> Notice that when Runner A conquers a zone from Runner B, Runner A's owned count increments, Runner B's decrements, and the total owned zone count across all runners strictly equals the number of claimed H3 hexagons—proving our Conservation of Territory law in action."

---

### Step 6: Benchmarks, Equivalence & Closing (1 Minute)
**Presenter Action:**
Click on the **📊 Benchmarks** tab inside Live Simulation (or inspect `data/reports/benchmark_results.csv`).

**Presenter Speech:**
> "Finally, let's review our academic benchmarks across all 3 verified scales:
> - **100K Records (11.22 MB):** 99.77 s | **1,002.3 rec/s**
> - **500K Records (56.77 MB):** 155.45 s | **3,216.4 rec/s**
> - **1M Records (113.88 MB):** 259.11 s | **3,859.3 rec/s**
> - Notice the sub-linear scaling curve: as data scales by 10x, runtime increases by only 2.6x as Spark JVM overhead amortizes. Process memory remains steady at ~91 MB with zero leaks.
> - In our Phase 12 consistency validation and Phase 13 equivalence testing, replaying all 75,425 eligible points produced **5,075 claims, 308 initial captures, 4,729 takeovers, and 38 revisits**.
> - Every single one of the 308 final zone owners matched the batch pipeline with **zero mismatches (100% equivalence)**.
> - All 89 automated tests pass cleanly.
> This demonstrates complete mathematical and operational consistency between our batch and real-time architectures.
> Thank you, and we welcome your questions."

---

## Quick Reference Demonstration Commands Summary
| Action | PowerShell Command |
| :--- | :--- |
| **Activate Virtualenv** | `.\.venv\Scripts\Activate.ps1` |
| **Run Generator** | `python -m src.data_generator --records 5000 --runners 10 --output data/raw/gps_demo.csv` |
| **Run Spark Pipeline** | `python -m src.pipeline --input data/raw/gps_100k.csv` |
| **Run Benchmarks** | `.\scripts\run_benchmarks.ps1 -Scales "100k"` |
| **Launch Dashboard** | `powershell -ExecutionPolicy Bypass -File scripts\start_project.ps1` |
| **Run Equivalence Test** | `python -m pytest tests/test_replay_integration.py -k test_batch_vs_replay_full_equivalence` |
| **Run Complete Test Suite**| `python -m pytest` |
