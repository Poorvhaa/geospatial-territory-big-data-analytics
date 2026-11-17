# Day 2 Execution Results & Technical Audit Report

**Timestamp (UTC):** 2026-10-26T19:11:32.373097+00:00  
**Validation Status:** ✅ PASSED (All 4 Core Invariants Satisfied)  
**Total Execution Duration:** 38.495 seconds  

---

## 1. Executive Performance Benchmarks

| Processing Phase | Execution Duration (seconds) |
| :--- | :--- |
| PySpark Ingestion | 0.558s |
| Data Cleaning & Kinematics | 4.044s |
| Kinematic Cheating Detection | 2.796s |
| Run Eligibility Filtering | 1.291s |
| Uber H3 Indexing (Res 9) | 0.177s |
| Territory Ownership Engine | 11.082s |
| Analytics & Leaderboards | 3.695s |
| Parquet Multi-Dataset Storage | 13.265s |
| **Total End-to-End Processing** | **38.495s** |

---

## 2. Ingestion & Data Quality Audit

- **Raw GPS Records Ingested:** 10
- **Valid Cleaned Records:** 10
- **Quarantined Records:** 0
- **Eligible GPS Points for Territory Conquest:** 6
- **Excluded Ineligible Runs:** 1

---

## 3. Cheating Detection Performance

- **Precision:** 1.0000
- **Recall:** 1.0000
- **F1 Score:** 1.0000

### Confusion Matrix (Ground Truth Evaluation):
- **True Positives (Cheating correctly flagged):** 1
- **False Positives (Clean runs falsely flagged):** 0
- **True Negatives (Clean runs correctly accepted):** 2
- **False Negatives (Cheaters missed):** 0

### Risk Category Distribution:
- **HIGH_RISK:** 1 runs (33.33%)
- **NORMAL:** 2 runs (66.67%)

---

## 4. Territory Conquest Summary

- **Total Valid Claims Generated:** 2
- **Unique Hexagonal Zones Owned (Res 9):** 1
- **Initial Zone Captures:** 1
- **Territory Takeovers (Ownership Transfers):** 1
- **Same-Owner Revisits (Non-Takeovers):** 0

### Top 10 Territory Owners (Current Leaderboard):

| Rank | Runner ID | Zones Owned |
| :--- | :--- | :--- |
| 1 | `runner_B` | 1 |

### Top 10 Most Contested Zones:

| Rank | H3 Cell Index | Takeovers | Unique Runners | Total Claims |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `892664c1a8fffff` | 1 | 2 | 2 |

---

## 5. Architectural Verification of Invariants

- [x] **Leaderboard Sum Conservation:** Total currently owned zones exactly equals the sum across the current ownership leaderboard.
- [x] **Claim Provenance Integrity:** 100% of current owners originate from verified eligible claims.
- [x] **Cheater Exclusion:** Zero suspicious or high-risk runs acquired territory.
- [x] **Revisit Immunity:** Same-owner revisits strictly excluded from takeover counts.
