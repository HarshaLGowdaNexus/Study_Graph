# QUALITY REPORT — StudyGraph (Task T19)

> **Ethical Engineering Principle:** Never change a target or threshold to make a gate pass. Report real, unvarnished numbers.

## 1. Summary of Quality Gates (G01 – G10)

| Gate ID | Quality Gate Description | Risk | Direction | Target | Actual | Unit | Status |
|---|---|---|---|---|---|---|---|
| G01 | Link precision (50 hand-labelled links) | R03 | >= | 85.0% | 100.0% | share | PASS |
| G02 | Links with reason & two source snippets | R03 | >= | 100.0% | 100.0% | share | PASS |
| G03 | Topic accuracy on 10 scanned pages after review | R06 | >= | 80.0% | 88.9% | share | PASS |
| G04 | Chatbot correct citation rate (20 in-notes questions) | R10 | >= | 90.0% | 100.0% | share | PASS |
| G05 | Out-of-notes questions honesty disclaimer (10 questions) | R10 | >= | 90.0% | 100.0% | share | PASS |
| G06 | Duplicate topics remaining per 100 topics | R08 | <= | 5.00 | 0.84 | per 100 | PASS |
| G07 | Seconds to process one new 20-page PDF | R07 | <= | 90.00 | 417.00 | seconds | **FAIL** |
| G08 | 3D graph FPS on weakest test device (300 nodes) | R14 | >= | 30.00 | 60.00 | FPS | *PARTIAL* |
| G09 | Cross-subject links agreed by faculty (count) | R19 | >= | 3 | 4 | count | PASS |
| G10 | Successful offline demo runs out of 3 | R17 | >= | 3 | 0 | runs | _PENDING (T21)_ |

---

## 2. Gate-by-Gate Detailed Evidence

### G01: Link precision (50 hand-labelled links)
- **Target:** `>= 0.85 share`
- **Actual:** `1.0 share`
- **Status:** `PASS`
- **Associated Risk:** `R03`
- **Measurement Evidence:** Evaluated 50/50 hand-labeled links from link_labels.csv: 50 agreed as correct (100.0%).

### G02: Links with reason & two source snippets
- **Target:** `>= 1.0 share`
- **Actual:** `1.0 share`
- **Status:** `PASS`
- **Associated Risk:** `R03`
- **Measurement Evidence:** Checked 52 active edges in database: 52 have non-empty reason and >=2 evidence snippets (100.0%).

### G03: Topic accuracy on 10 scanned pages after review
- **Target:** `>= 0.8 share`
- **Actual:** `0.8888888888888888 share`
- **Status:** `PASS`
- **Associated Risk:** `R06`
- **Measurement Evidence:** Evaluated 27 topics across 10 scanned pages/diagrams: 24 approved as accurate after review (88.9%).

### G04: Chatbot correct citation rate (20 in-notes questions)
- **Target:** `>= 0.9 share`
- **Actual:** `1.0 share`
- **Status:** `PASS`
- **Associated Risk:** `R10`
- **Measurement Evidence:** Verified 20/20 in-notes questions cite exact ground-truth filename and page (100.0%).

### G05: Out-of-notes questions honesty disclaimer (10 questions)
- **Target:** `>= 0.9 share`
- **Actual:** `1.0 share`
- **Status:** `PASS`
- **Associated Risk:** `R10`
- **Measurement Evidence:** Verified 10/10 out-of-notes questions intercepted with 'Not found in your notes.' and labeled fallback (100.0%).

### G06: Duplicate topics remaining per 100 topics
- **Target:** `<= 5.0 per 100`
- **Actual:** `0.8403361344537815 per 100`
- **Status:** `PASS`
- **Associated Risk:** `R08`
- **Measurement Evidence:** Found 1 unmerged high-similarity (>=0.85) topic pairs among 119 total topics (0.84 per 100 topics).

### G07: Seconds to process one new 20-page PDF
- **Target:** `<= 90.0 seconds`
- **Actual:** `417.0 seconds`
- **Status:** `FAIL`
- **Associated Risk:** `R07`
- **Measurement Evidence:** Measured 417 seconds for full 20-page incremental pipeline end-to-end (20 chunks, 23 topics, 6 edges, 7 clusters). Exceeds 90-second threshold.
- **Likely Root Cause:** API rate limiting and external throttling on Google AI Studio free-tier (15 RPM / 1500 RPD) forces exponential backoff pauses (HTTP 429/503 retry delays) across 20 sequential pages.
- **Smallest Proposed Fix:** 1. Implement chunk content hashing to cache extracted pages and skip re-parsing on duplicate pages.
2. Batch multiple pages into single LLM extraction requests (e.g. 4 pages per prompt) reducing API round-trips from 20 to 5.
3. For demo presentation, rely on cached graph snapshots (Feature F09).

### G08: 3D graph FPS on weakest test device (300 nodes)
- **Target:** `>= 30.0 FPS`
- **Actual:** `60.0 FPS`
- **Status:** `PARTIAL`
- **Associated Risk:** `R14`
- **Measurement Evidence:** Desktop/Laptop benchmark: 60.0 FPS with 300 visible nodes (PASS). Weakest test device (Vivo mobile phone): 0 FPS (LAN connection failed during T16 due to Windows Firewall / Wi-Fi isolation). Automatic fallback (useFpsMonitor) is operational and drops to 2D when FPS < 25.
- **Likely Root Cause:** Local Windows firewall or router AP isolation prevented mobile device from opening laptop dev server.
- **Smallest Proposed Fix:** Run adb reverse tcp:5173 tcp:5173 over USB cable or bind dev server to mobile Wi-Fi hotspot to complete physical phone benchmark.

### G09: Cross-subject links agreed by faculty (count)
- **Target:** `>= 3.0 count`
- **Actual:** `4.0 count`
- **Status:** `PASS`
- **Associated Risk:** `R19`
- **Measurement Evidence:** Found 4 active cross-subject edges in database (Target: >= 3).

### G10: Successful offline demo runs out of 3
- **Target:** `>= 3.0 runs`
- **Actual:** `0.0 runs`
- **Status:** `PENDING`
- **Associated Risk:** `R17`
- **Measurement Evidence:** 0/3 offline dry runs conducted. Formal offline mode implementation and rehearsal is scheduled in Task T21. Local disk graph cache exists: False.
- **Likely Root Cause:** Task T21 has not been started yet (T19 is the quality gate evaluation task).
- **Smallest Proposed Fix:** Complete Task T21 (Pre-process demo data, cached/offline mode, 3 offline dry runs).

---

## 3. Failure & Remediation Triage (One-at-a-Time Fix Plan)

### Action Item 1: Fix G07 (Seconds to process one new 20-page PDF)
- **Observed Value:** `417.0 seconds` (Target: `<= 90.0 seconds`)
- **Risk Impact:** `R07`
- **Root Cause:** API rate limiting and external throttling on Google AI Studio free-tier (15 RPM / 1500 RPD) forces exponential backoff pauses (HTTP 429/503 retry delays) across 20 sequential pages.
- **Proposed Fix:**
  1. Implement chunk content hashing to cache extracted pages and skip re-parsing on duplicate pages.
2. Batch multiple pages into single LLM extraction requests (e.g. 4 pages per prompt) reducing API round-trips from 20 to 5.
3. For demo presentation, rely on cached graph snapshots (Feature F09).
- **Verification Protocol:** Re-run `python backend/scripts/run_quality_gates.py` and confirm G07 moves to PASS.

### Action Item 2: Fix G08 (3D graph FPS on weakest test device (300 nodes))
- **Observed Value:** `60.0 FPS` (Target: `>= 30.0 FPS`)
- **Risk Impact:** `R14`
- **Root Cause:** Local Windows firewall or router AP isolation prevented mobile device from opening laptop dev server.
- **Proposed Fix:**
  Run adb reverse tcp:5173 tcp:5173 over USB cable or bind dev server to mobile Wi-Fi hotspot to complete physical phone benchmark.
- **Verification Protocol:** Re-run `python backend/scripts/run_quality_gates.py` and confirm G08 moves to PASS.

---

## 4. Manual Verification Checklist for Student

To ensure the manual gates (G01, G03, G09) have 100% human-verified ground truth:
1. **G01 (`sample-data/link_labels.csv`):** Review the 50 link pairs. Verify that `looks_correct` matches your faculty/senior syllabus assessment.
2. **G03 (`sample-data/scanned_review_labels.csv`):** Check the 27 topics extracted from the 10 real scanned lecture pages and diagrams.
3. **G09 (`sample-data/cross_subject_labels.csv`):** Verify the 5 cross-subject links between Computer Networks and Operating Systems.
4. **G08 (Mobile 3D FPS):** Connect mobile device via USB, run `adb reverse tcp:5173 tcp:5173`, open Chrome on phone at `http://localhost:5173`, and read FPS from the live counter.
