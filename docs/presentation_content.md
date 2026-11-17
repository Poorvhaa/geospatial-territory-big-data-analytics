# Academic Presentation Content
## Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data
**Presentation Deck (12 Slides)**

---

### Slide 1: Project Title & Introduction
- **Title:** Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data
- **Subtitle:** Scalable Kinematic Validation, Hexagonal Conquest, and Real-Time Telemetry Simulation
- **Domain:** Geospatial Big Data Analytics, Distributed Computing, Location-Based Gamification
- **Presenter / Team:** Geospatial Big Data Engineering Team
- **Milestone:** Final Capstone Submission (Day 5 Certified Ready)
- **Key Focus:** Distributed data hygiene, rule-based fraud detection, Uber H3 spatial discretization, deterministic micro-batch replay, and 100K-1M empirical benchmarks.

---

### Slide 2: Problem Statement & Motivation
- **Context:** Mobile fitness platforms (Strava, Zwift, Ingress) track high-frequency GPS trajectories across millions of simultaneous athletes.
- **Key Challenges:**
  1. *GPS Sensor Jitter & Multipath Noise:* Consumer devices exhibit coordinate drift and instantaneous signal jumps.
  2. *Cheating & Leaderboard Spoofing:* Automated spoofers and athletes in cars compromise competitive fairness.
  3. *Continuous Geometric Cartesian Explosions:* Pairwise polygon intersections fail to scale horizontally.
  4. *Conquest Determinism:* High-concurrency claims require strict, reproducible tie-breaking rules.
  5. *Streaming & Batch Disconnect:* Keeping real-time leaderboards consistent with historical audits without redundant recomputations.

---

### Slide 3: Project Objectives
- **End-to-End Pipeline:** Develop a distributed, automated pipeline from raw GPS CSV ingestion to interactive BI visualization.
- **Kinematic Rule Engine:** Enforce biomechanical running constraints ($v \le 25 \text{ km/h}$, $|a| \le 8 \text{ m/s}^2$) to quarantine fraud.
- **Hexagonal Spatial Grid:** Discretize coordinates into Uber H3 Resolution 9 cells (~0.1 km²) for $O(1)$ spatial comparisons.
- **Stateful Territory Engine:** Model contiguous visits, enforce $k=2$ observation thresholds, and classify transitions (Initial Capture, Takeover, Revisit).
- **Simulated Real-Time Replay:** Build a persistent micro-batch replay engine with full playback controls (Start, Pause, Resume, Stop, Restart).
- **Academic Equivalence:** Prove 100% equivalence between batch conquest results and streaming replay outcomes.

---

### Slide 4: Big Data Characteristics (The 5 V's)
- **Volume:** Ingesting 100K to 1M trajectory records, generating hundreds of thousands of spatial states and transitions.
- **Velocity:** High-frequency 5-second sampling intervals requiring micro-batch stream processing and low-latency state persistence.
- **Variety:** Multimodal sensor telemetry combining WGS84 coordinates, heart rate (bpm), cadence (spm), elevation, and device metadata.
- **Veracity:** Rigorous data cleaning, temporal sequence enforcement ($\Delta t > 0$), and heuristic fraud isolation.
- **Value:** Transforming noisy raw coordinate streams into competitive gamified territory dominance and urban activity hotspot intelligence.

---

### Slide 5: Technology Stack & Architectural Justification
- **Apache PySpark 4.2.0:** Distributed ETL, Window functions for kinematics, and partitioned aggregations.
- **Uber H3 (v4.x):** Global discrete hexagonal indexing; converts complex geometry into 64-bit integer / hex string comparisons.
- **Apache Parquet & PyArrow:** Columnar, Snappy-compressed file format enabling sub-second analytical dashboard loads without driver memory bottlenecks.
- **SQLite 3 (WAL Mode):** ACID-compliant transactional local persistence for incremental simulation checkpoints and idempotency.
- **Streamlit & Folium:** Production BI dashboard with `@st.fragment` sub-second DOM updates and dark-theme interactive hexagonal cartography.
- **Python 3.11 & Pytest:** Modern typed architecture with 89 passing automated tests.

---

### Slide 6: System Architecture & Workflow
- **Stage 1 (Generation & Ingestion):** Seeded generator produces 100K-1M points; Spark loads data with explicit `StructType` schemas.
- **Stage 2 (Cleaning & Kinematics):** Haversine distance, speed, and acceleration derived via Spark Window specs.
- **Stage 3 (Fraud Detection):** Teleportation, driving, and noise spikes flagged; non-eligible runs quarantined.
- **Stage 4 (Spatial Discretization):** Eligible points projected to H3 Resolution 9 hex cells.
- **Stage 5 (Territory Engine):** Contiguous visits segmented with $k \ge 2$; transitions classified chronologically.
- **Stage 6 (Storage & Analytics):** Columnar Parquet export; incremental hotspot scoring ($0.40T + 0.35U + 0.25V$).
- **Stage 7 (Real-Time Replay):** Micro-batch coordinator updates SQLite state store with zero batch duplication.

---

### Slide 7: GPS Data Generation & Distributed Cleaning
- **Realistic Urban Tracks:** Seeded generation around 7 Chicago hubs (Millennium Park, Grant Park, Lakefront Trail, Riverwalk).
- **6 Behavioral Scenarios:** Normal Run (55%), Fast Run (10%), Walking (10%), Driving (10%), Teleportation (10%), GPS Noise (5%).
- **PySpark Cleaning Pipeline:**
  - Latitude bounds: $[-90.0, 90.0]$, Longitude bounds: $[-180.0, 180.0]$.
  - Temporal sequence: $t_i - t_{i-1} > 0$.
  - Exact Haversine spherical distance evaluated in PySpark SQL.
  - Kinematic derivatives: instantaneous speed ($v$) and acceleration ($a$).

---

### Slide 8: Rule-Based Cheating Detection
- **Biomechanical Constraints Evaluated:**
  - *Impossible Speed:* $v > 25.0 \text{ km/h}$.
  - *Teleportation:* Jump $\ge 300\text{ m}$ or instantaneous speed $\ge 80\text{ km/h}$.
  - *Driving Pattern:* Speed $\ge 25\text{ km/h}$ and cadence $\le 50\text{ spm}$ over $\ge 3$ consecutive points.
  - *Abnormal Acceleration:* $|a| \ge 8.0\text{ m/s}^2$.
  - *GPS Multipath Noise:* Chord return distance $\le 35\text{ m}$ isolates noise spikes without penalizing athletes.
- **Run Risk Scoring:** Composite formula categorizes runs into NORMAL, SUSPICIOUS, or HIGH_RISK.
- **100K Dataset Empirical Results:** 943 NORMAL runs approved, 168 SUSPICIOUS and 139 HIGH_RISK quarantined (307 fraudulent runs excluded from claiming).

---

### Slide 9: Uber H3 Hexagonal Territory Ownership Engine
- **Spatial Resolution 9:** Hexagons with area $\sim 0.105\text{ km}^2$ and edge length $174.38\text{ m}$.
- **Conquest Rules:**
  - *Contiguous Visits:* Moving out of a cell and returning creates a new discrete visit (re-entry support).
  - *Consecutive Observation Threshold ($k=2$):* Claims are confirmed only at the 2nd consecutive point in a cell.
  - *Deterministic Tie-Breaking:* Claims sorted by `(claim_timestamp_epoch, run_id, runner_id, claim_id)`.
  - *Transition Classification:*
    - **INITIAL_CAPTURE:** First capture of unowned cell.
    - **TAKEOVER:** Conquest of a cell held by a competitor ($P_{\text{current}} \ne P_{\text{previous}}$).
    - **SAME_OWNER_REVISIT:** Additional visit by current owner (no takeover counted).

---

### Slide 10: Production BI Dashboard & Analytics (Day 5 Redesign)
- **Multi-View Analytics Platform (Territory Intelligence):**
  - *Executive Overview:* 8 real KPI metric cards, activity trends, risk distribution donuts, and 7-metric Analytical Insights briefing.
  - *Territory Cartography:* Folium map with 4 distinct layers (Territory Ownership, Activity Heatmap, Contested Zones, Recent Captures) and on-screen color legend.
  - *Dynamic Leaderboard:* Ranks athletes by currently held territory with verified $\sum \text{zones\_owned} == 308$ reconciliation banner.
  - *Hotspot Analysis:* Explainable composite scores ($0.40T + 0.35U + 0.25V$), dynamic natural language interpretations, and zone drill-down inspector.
  - *Fraud Analytics:* Individual run explainability deep-dive, confusion matrices (Precision 80.13%, Recall 100%, F1 0.8897), and anomaly breakdowns.
  - *Runner Explorer:* Individual athlete dossiers, pace profiles, and trophy cabinets.

---

### Slide 11: Real-Time GPS Simulation & Big Data Benchmarking
- **Decoupled Architecture:** Background `ReplayEngine` thread advances micro-batches without blocking the Streamlit UI.
- **Replay Controls:** Fully functioning START, PAUSE, RESUME, STOP, and RESTART with 1x, 2x, 5x, and 10x speeds.
- **Empirical Benchmarking Across 3 Full Scales (Windows 11 / Spark 4.2.0 local[2]):**
  - **100K Records (11.22 MB):** 99.77 s | **1,002.3 rec/s** | Peak RAM: 91.0 MB
  - **500K Records (56.77 MB):** 155.45 s | **3,216.4 rec/s** | Peak RAM: 90.6 MB
  - **1M Records (113.88 MB):** 259.11 s | **3,859.3 rec/s** | Peak RAM: 90.9 MB
- **Sub-Linear Scalability:** Increasing volume 10x increases runtime by only 2.6x, demonstrating high JVM JIT efficiency and zero memory leaks.

---

### Slide 12: Empirical Findings, Limitations & Future Scope
- **Key Empirical Finding:** Exact **100% equivalence** achieved between batch conquest and real-time replay across 75,425 points:
  - Total Claims: 5,075 | Current Zones: 308 | Initial Captures: 308 | Takeovers: 4,729 | Revisits: 38.
  - **Zero owner mismatches** across all 308 zones.
- **Testing & Verification:** 89 automated tests (100% passing) across unit, integration, and mathematical consistency invariants.
- **Limitations:** Micro-batch replay simulator (not production Kafka/Flink streaming); single-node local execution.
- **Future Directions:** Live Kafka/MQTT telemetry ingest, Flink sliding-window online CEP, and 3D elevation modeling.
- **Conclusion:** A robust, cheat-resilient, mathematically verified geospatial big data architecture certified ready for academic capstone defense.
