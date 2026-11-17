# Territory Intelligence - Localhost Run Guide

**Project Title:** Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data  
**Location:** `D:\BDA`  
**Dashboard URL:** [http://localhost:8501](http://localhost:8501)  
**Last Updated:** October 30, 2026

---

## 1. Environment Details

The application runs directly in the dedicated local Windows virtual environment:

- **Operating System:** Windows 11 64-bit
- **Python Version:** 3.11.5 (`D:\BDA\.venv\Scripts\python.exe`)
- **Java Runtime:** Java JDK 23.0.2 (`JAVA_HOME = C:\Program Files\Java\jdk-23`)
- **Apache PySpark:** 4.2.0 (`local[2]`, memory `2g`, 4 shuffle partitions)
- **Uber H3:** 4.5.0 (Resolution 9 hexagons, ~0.1 km² area, 174m edge length)
- **Streamlit:** 1.66.1 (Interactive BI Dashboard)
- **Pandas:** 3.1.0
- **PyArrow:** 26.0.0
- **Plotly:** 7.1.0
- **Folium / Leaflet:** 0.20.0 (`streamlit-folium`)

---

## 2. Launching the Application on Localhost

### Method A: One-Click PowerShell Script (Recommended)

From the project root `D:\BDA`, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_project.ps1
```

This automated script performs pre-flight checks:
1. Validates the `.venv` Python executable.
2. Verifies core dependencies (`streamlit`, `pyspark`, `h3`, `folium`, `plotly`, `pyarrow`, `pandas`, `yaml`).
3. Confirms analytical Parquet datasets exist under `data/parquet/`.
4. Checks that `dashboard/app.py` is present.
5. Verifies port availability on port `8501`.
6. Launches Streamlit on `http://localhost:8501`.

### Method B: Direct Virtual Environment Command

```powershell
Set-Location "D:\BDA"
& ".\.venv\Scripts\python.exe" -m streamlit run "dashboard\app.py" --server.port 8501 --server.address localhost
```

---

## 3. Opening the Dashboard in Your Browser

Once launched, open your web browser (Chrome, Edge, Firefox, Brave) and navigate to:

👉 **[http://localhost:8501](http://localhost:8501)**

---

## 4. How to Stop and Restart the Server

### Stopping the Server
- If running in an interactive terminal, press:
  ```text
  Ctrl + C
  ```
- To stop a background Streamlit server on port 8501 via PowerShell:
  ```powershell
  $conn = Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue
  if ($conn) {
      $pids = $conn | Select-Object -ExpandProperty OwningProcess -Unique
      Stop-Process -Id $pids -Force
      Write-Host "Stopped Streamlit process (PIDs: $($pids -join ', '))"
  }
  ```

### Restarting the Server
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_project.ps1
```

---

## 5. System Health Check

Before or after launching, run the system audit script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_project.ps1
```

This verifies:
- Python 3.11.5 in `.venv`
- Java 23 & `JAVA_HOME`
- PySpark, Uber H3, Streamlit, and core packages
- Required configuration and code files
- Raw CSV datasets (`gps_100k.csv`, `gps_500k.csv`, `gps_1m.csv`)
- Analytical Parquet tables in `data/parquet/`
- Streamlit service status on port 8501
- Pytest suite availability (18 test suites)

---

## 6. How to Run Automated QA Tests

Execute the complete regression test suite using pytest:

```powershell
# Quiet mode (recommended)
& ".\.venv\Scripts\python.exe" -m pytest -q

# Verbose mode
& ".\.venv\Scripts\python.exe" -m pytest -v

# Run only dashboard tests
& ".\.venv\Scripts\python.exe" -m pytest tests/test_dashboard.py -v

# Run data consistency & integrity tests
& ".\.venv\Scripts\python.exe" -m pytest tests/test_data_consistency.py -v

# Run Spark smoke test
& ".\.venv\Scripts\python.exe" -m src.spark_session
```

**Verified Test Results:**
- **89 passed, 3 warnings** across all 18 test suites.

---

## 7. How to Process GPS Data (Pipeline Execution)

The project includes pre-compiled, verified analytical Parquet tables under `data/parquet/`. If you want to re-execute the end-to-end Big Data pipeline on raw GPS telemetry:

```powershell
# Re-run pipeline on the 100k dataset
& ".\.venv\Scripts\python.exe" -m src.pipeline --input data/raw/gps_100k.csv --output data/parquet --h3-resolution 9 --min-consecutive 2
```

Supported pipeline CLI arguments:
- `--input`: Path to input CSV (default: `data/raw/gps_100k.csv`)
- `--output`: Output Parquet directory (default: `data/parquet`)
- `--h3-resolution`: Uber H3 grid resolution (default: `9`)
- `--min-consecutive`: Minimum consecutive points to validate a zone claim (default: `2`)

---

## 8. Dashboard Navigation Guide

The platform consists of 8 high-performance views accessible via the sidebar navigation:

1. **📊 Overview:**
   - 8 Executive KPIs: Total GPS Records (100,000), Active Runners (250), Valid Activities (943), Current Zones (308), Ownership Takeovers (4,729), Contested Zones (233), Suspicious Runs (307), Processing Status (`SYNCHRONIZED PASS`).
   - Macro temporal charts, risk distribution donut, and top territory owners.

2. **⚡ Live Simulation:**
   - Bi-temporal micro-batch streaming engine with playback controls (`START`, `PAUSE`, `RESUME`, `STOP`, `RESTART`).
   - Playback multipliers (1x, 2x, 5x, 10x).
   - Real-time map displaying initial captures (green glow) and takeovers (crimson glow).
   - Live event feed, dynamic leaderboard, and runtime benchmarks.

3. **🗺️ Territory Map:**
   - Full Uber H3 Resolution 9 hexagonal boundary rendering across Chicago Loop.
   - 4 Interactive Layer Modes:
     - *Territory Ownership:* Deterministic high-contrast color palette per runner.
     - *Activity Heatmap:* Color gradient from low traffic to high-intensity hubs.
     - *Contested Zones:* Color gradient identifying heavily disputed battlegrounds.
     - *Recent Captures:* Chronological recency gradient.
   - Interactive Zone Inspector: Cell ID, Current Owner, Takeover count, and full conquest audit history.

4. **🏆 Leaderboard:**
   - Multi-metric ranking: Zones Owned, Total Captures, Takeovers, Valid Runs, Distance Traversed.
   - Mathematical Conservation of Territory banner verifying 100% reconciliation ($\sum \text{Zones Owned} \equiv 308$).
   - CSV export functionality.

5. **🔥 Hotspot Analysis:**
   - Spatial clustering of contested zones and hostile takeovers.
   - Composite hotspot score incorporating visits, unique runners, and takeovers.

6. **🛡️ Cheat Detection:**
   - Kinematic anomaly evaluation: Teleportation, Motor Vehicle Transit (Driving), Impossible Acceleration, GPS Noise Spikes.
   - Run-level fraud risk categorization (`NORMAL`, `SUSPICIOUS`, `HIGH_RISK`).
   - Performance evaluation matrix (Precision 80.1%, Recall 100.0%, F1 89.0%).

7. **📈 Activity Analytics:**
   - Temporal velocity and cadence distributions.
   - Diurnal and hourly activity transit trends.
   - Speed vs. heart rate kinematic correlations.

8. **🏃 Runner Explorer:**
   - Individual runner dossier and spatial footprint.
   - Historical route visualizer, defended zones, and personal conquest timeline.

*(Note: "Territory Battles" features are integrated directly across the Territory Map, Hotspot Analysis, and Live Simulation rather than as a standalone disconnected sub-page).*

---

## 9. Common Errors and Troubleshooting

### Error: `StreamlitInvalidHeightError: Invalid height value: None.`
- **Cause:** In Streamlit 1.66+, passing `height=None` to `st.dataframe` is disallowed.
- **Fix:** Fixed in `dashboard/components/tables.py` by checking `if height is not None: kwargs["height"] = height` and omitting `height` when `None`.

### Warning: `PySpark does not yet fully support pandas >= 3.0.0`
- **Cause:** Pandas 3.1.0 is installed alongside PySpark 4.2.0.
- **Impact:** Informational warning only. All 89 automated tests, PySpark DataFrame calculations, and Parquet operations execute successfully without runtime incompatibility.

### Error: `ModuleNotFoundError: No module named 'src'` when executing a script directly
- **Cause:** Invoking a script directly (`python src/pipeline.py`) without `D:\BDA` on `sys.path`.
- **Fix:** Resolved by auto-injecting project root into `sys.path` in `src/pipeline.py` and `src/spark_session.py`, or invoking as a module (`python -m src.pipeline`).

### Issue: Port 8501 is already in use
- **Cause:** A previous Streamlit server process is still running.
- **Fix:** Run `scripts/check_project.ps1` to detect the PID, or use the PowerShell stop command in Section 4 above.

---

## 10. Remaining Limitations

1. **Local Single-Node Deployment:** PySpark operates in `local[2]` mode suitable for local workstation execution (up to 1M GPS records). Clustered execution (YARN/Kubernetes) is not configured in this local environment.
2. **Synthetic Telemetry:** Data represents simulated Chicago Loop runners covering 308 H3 Resolution 9 hexagonal zones.
3. **Headless Browser Capability:** Visual screenshots require an interactive GUI session; all internal rendering pipelines, widget states, and DOM layouts were verified with Streamlit AppTest and curl HTTP status probes.
