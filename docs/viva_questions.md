# Viva Voce & Technical Defense Questions
## Real-Time Territory Control and Hotspot Analysis Using Geospatial Big Data
**20 Key Examination Questions with Accurate Answers**

---

### Q1: Why use Apache PySpark instead of pure Pandas for this project?
**Answer:** Pure Pandas is constrained to single-node memory and execution on a single core. As geospatial datasets scale to hundreds of thousands or millions of GPS points, operations like windowed kinematic calculations, spherical Haversine distances, and temporal sorting exceed single-machine RAM and cause Out-Of-Memory (OOM) crashes. PySpark distributes DataFrame partitions across multiple CPU cores or cluster worker nodes, allowing parallel computation with lazy execution plans and cost-based query optimization.

---

### Q2: What is Uber H3, and why was it chosen over standard latitude/longitude bounding boxes or PostGIS polygons?
**Answer:** Uber H3 is a discrete global grid system that partitions the Earth's surface into regular hexagonal cells. Hexagons have a unique mathematical property: all adjacent neighbors are equidistant (unlike squares where diagonals are $\sqrt{2}$ times further). Projecting continuous coordinates into H3 indices transforms complex spherical geometry and spatial containment queries into $O(1)$ string/hash equality comparisons, completely eliminating expensive spatial joins and R-Tree intersections.

---

### Q3: What spatial resolution was selected for H3, and what geographic area does it represent?
**Answer:** Resolution 9 was selected. At Resolution 9, an H3 hexagonal cell has an average area of approximately $0.105 \text{ km}^2$ ($105,332 \text{ m}^2$) and an average edge length of $174.38 \text{ meters}$. This granularity represents roughly one to two urban city blocks—ideal for running routes, neighborhood conquests, and competitive sprint segments.

---

### Q4: Why is the Haversine formula preferred over simple Euclidean distance for GPS coordinates?
**Answer:** GPS coordinates (latitude and longitude) are spherical angular coordinates on an oblate spheroid, not Cartesian planar coordinates. Euclidean distance ($\sqrt{\Delta x^2 + \Delta y^2}$) causes severe distortion as latitude deviates from the equator. The Haversine formula accounts for the Earth's mean radius ($R \approx 6,371,000 \text{ meters}$) and spherical curvature to calculate the true great-circle distance between two points.

---

### Q5: How does the system detect vehicle driving when an athlete is supposed to be running?
**Answer:** Driving detection evaluates a multi-modal feature combination over a sliding window:
1. Instantaneous speed exceeds running limits: $v_i \ge 25.0 \text{ km/h}$.
2. Cadence telemetry is abnormally low: $\text{cadence} \le 50 \text{ steps/min}$ (or null).
3. The pattern is sustained over $\ge 3$ consecutive observations.
A human cannot run at 40 km/h with a cadence of 20 spm; this kinematic discrepancy reliably flags motor vehicle movement.

---

### Q6: How does the algorithm distinguish between GPS multipath noise and GPS teleportation (spoofing)?
**Answer:** Teleportation is an unnatural jump where the runner leaps hundreds of meters and continues moving from the new location ($d \ge 300\text{ m}$ or $v \ge 80\text{ km/h}$). Isolated GPS noise is a momentary reflection off tall buildings where point $i$ spikes by $\ge 50\text{ m}$, but point $i+1$ immediately returns to the normal track within 35 meters of point $i-1$. By evaluating the "chord distance" between points $i-1$ and $i+1$, the system isolates transient noise without penalizing the athlete.

---

### Q7: Why is a minimum consecutive observation threshold ($k=2$) required before awarding a territory claim?
**Answer:** Without a consecutive observation threshold, a runner merely grazing the peripheral boundary of a hexagon or experiencing a single GPS jitter point would instantaneously capture the zone. Requiring $k=2$ consecutive observations verifies intentional spatial entry and dwell time within the hexagonal cell before confirming the claim.

---

### Q8: What are the three territory transition types, and how are they classified?
**Answer:**
1. **INITIAL_CAPTURE:** The hexagon had no prior owner; a runner establishes the very first claim.
2. **TAKEOVER:** The hexagon was currently owned by Runner $A$, and Runner $B$ ($B \ne A$) logs an eligible claim. Ownership transfers to $B$, and the zone's takeover count increments.
3. **SAME_OWNER_REVISIT:** The hexagon is currently owned by Runner $A$, and Runner $A$ visits it again. Ownership does not change, and the takeover count does NOT increment.

---

### Q9: How is deterministic tie-breaking handled when two runners claim a zone with identical timestamps?
**Answer:** In distributed systems, relying solely on timestamps can cause non-deterministic sorting across different partitions or runs. The territory engine enforces a secondary, deterministic composite tie-breaker:
$$\text{Order Key} = (\text{claim\_timestamp\_epoch ASC}, \text{run\_id ASC}, \text{runner\_id ASC}, \text{claim\_id ASC})$$
This guarantees identical results across both batch processing and streaming replay.

---

### Q10: What is the "Conservation of Territory" rule in the leaderboard?
**Answer:** The Conservation of Territory rule states that at any given moment:
$$\sum_{r \in \text{Runners}} \text{Zones Currently Owned}(r) \equiv \text{Total Unique Hexagons Claimed}$$
When Runner $A$ takes over a zone from Runner $B$, $A$'s count increments by 1, $B$'s count decrements by 1, and the net total of currently held zones remains unchanged. This prevents cumulative captures from being confused with current territory dominance.

---

### Q11: How is the composite Hotspot Score calculated, and why are its weights chosen?
**Answer:** The Hotspot Score quantifies urban zone activity and contention:
$$\text{Score} = 0.40 \cdot \tilde{T} + 0.35 \cdot \tilde{U} + 0.25 \cdot \tilde{V}$$
Where $\tilde{T}$ is normalized takeovers, $\tilde{U}$ is normalized unique runners, and $\tilde{V}$ is normalized total visits. Takeovers receive the highest weight (0.40) because frequent ownership changes indicate competitive contestation. Unique runners (0.35) reflect broad athletic popularity, while total visits (0.25) account for overall volume.

---

### Q12: Why was SQLite chosen with WAL mode for the real-time simulation state store?
**Answer:** SQLite is an ACID-compliant, serverless, zero-configuration relational database ideal for local embedded persistence. Write-Ahead Logging (WAL) mode allows concurrent readers to query live metrics and maps while the background simulation thread writes micro-batch commits, preventing database lock contention.

---

### Q13: How does the system prevent duplicate claim processing and duplicate batch submissions?
**Answer:**
1. **Batch Idempotency:** The `committed_batches` table records `(session_id, batch_id)`. If an already committed batch is submitted, it is rejected immediately.
2. **Claim Idempotency:** The `ownership_history` table uses `claim_id` as a primary key with `INSERT OR IGNORE`. In-memory state tracking maintains a set of seen claim IDs.

---

### Q14: How does the replay simulator handle a runner whose single visit spans across two micro-batches?
**Answer:** The `BatchProcessor` maintains an `ActiveRunState` dictionary in memory. If point 1 of a run occurs at the end of Batch 1 and point 2 occurs at the start of Batch 2, the runner's visit count increments from 1 to 2 across the batch boundary, and the claim is correctly confirmed and emitted in Batch 2. Run state is never reset prematurely at batch boundaries.

---

### Q15: What is the difference between Option A (in-flight run buffering) and Option B (prevalidated replay)?
**Answer:**
- **Option A:** Buffers incomplete runs in memory during streaming and holds back territory awards until the entire run finishes and fraud scoring completes. Requires rollback mechanics if a run is later invalidated.
- **Option B (Implemented):** Evaluates run eligibility in a prevalidation phase using Day 2 kinematic heuristics, then streams only eligible points in chronological order. This ensures 100% deterministic validation, eliminates speculation, and clearly separates streaming mechanics from batch fraud classification.

---

### Q16: What were the actual batch vs. replay equivalence results on the 100K dataset?
**Answer:** The equivalence test verified:
- Total claims: **5,075** in batch vs. **5,075** in replay (100% match).
- Active zones: **308** in batch vs. **308** in replay (100% match).
- Initial captures: **308** in batch vs. **308** in replay (100% match).
- Takeovers: **4,729** in batch vs. **4,729** in replay (100% match).
- Same-owner revisits: **38** in batch vs. **38** in replay (100% match).
- Current zone owners: **Zero mismatches** across all 308 zones.

---

### Q17: Why did you use Streamlit fragments (`@st.fragment`) instead of full-page reruns?
**Answer:** Traditional Streamlit reruns re-execute the entire Python script from top to bottom on every user interaction, causing screen flickering, high CPU usage, and resetting map pan/zoom. `@st.fragment(run_every=1.0)` isolates updates strictly to the simulation controls, KPIs, and live map, rendering smooth sub-second updates without triggering app-level script re-execution.

---

### Q18: What is the benefit of Parquet columnar storage over CSV for the BI dashboard?
**Answer:** CSV is an unindexed, uncompressed row-based text format requiring full parsing of every column and row. Parquet is a binary columnar format with Snappy compression and dictionary encoding. The BI dashboard reads only the specific columns needed (e.g., `h3_cell`, `current_owner_id`) using PyArrow, reducing disk I/O by over 80% and achieving sub-second page loads without loading raw multi-million point GPS tables.

---

### Q19: What were the measured throughputs and scalability trends across 100K, 500K, and 1M records?
**Answer:**
Empirical benchmarking on Windows 11 with PySpark local[2] recorded:
- **100K:** 99.77 s (**1,002.3 records/second**) | Ingest: 9.7s | Cleaning: 19.6s | Parquet: 26.3s
- **500K:** 155.45 s (**3,216.4 records/second**) | Ingest: 14.9s | Cleaning: 27.8s | Parquet: 53.2s
- **1M:** 259.11 s (**3,859.3 records/second**) | Ingest: 42.5s | Cleaning: 98.0s | Parquet: 53.2s

**Key Insight:** Processing throughput scales sub-linearly (10x record volume requires only 2.6x duration). Fixed overhead (JVM launch, catalog initialization, schema reflection) amortizes over larger datasets, increasing throughput from ~1,000 to nearly 3,860 records/second while maintaining constant ~91 MB process memory. The primary bottlenecks at 1M scale are windowed kinematic calculations and multi-table Parquet writes.

---

### Q20: What are the main limitations of the current implementation, and how would you deploy it in production?
**Answer:**
- **Current Limitations:** Local single-node execution on 2 CPU cores; prevalidation model rather than live online Kafka streaming.
- **Production Architecture:**
  1. Ingest telemetry streams via **Apache Kafka** clusters.
  2. Implement stateful stream processing via **Apache Flink** with tumbling session windows for online fraud scoring.
  3. Deploy PySpark batch pipelines on **Kubernetes / Databricks / AWS EMR**.
  4. Store current ownership state in **Redis / Amazon DynamoDB** for sub-millisecond global leaderboard queries.
