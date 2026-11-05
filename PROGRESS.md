# PROGRESS (you update this after every task)

Status values: Not started | Plan approved | Built - waiting for my test | Done (I said TEST PASSED) | Blocked
Only I can move a task to Done, by writing TEST PASSED Txx. You then update this file.

| Task | What | Status | Date | Git commit | Notes |
|---|---|---|---|---|---|
| T01 | Create repo, database and storage project, schema (Data Model sheet), API keys | Done | 2026-11-04 | T01: Initial project skeleton, database migration, and connection check | Skeleton, .env.example, SQL migration with 20 tables & pgvector, connection verified |
| T02 | Collect REAL data: 2-3 subjects of class notes (typed + scanned), 1 textbook, 3+ previous-year papers | Done | 2026-11-05 | T02: Sample data structure, ground truth CSV templates, and validator | sample-data folder structure, 3 CSV templates (manifest, test_questions, link_labels), check_sample_data.py validator |
| T03 | Upload + folder structure + storage + job queue with progress | Not started |  |  |  |
| T04 | Text extraction + vision OCR with page numbers | Not started |  |  |  |
| T05 | Topic extraction (keyword, 1-4 lines, real-world use, source chunks) | Not started |  |  |  |
| T06 | Review screen (skippable) | Not started |  |  |  |
| T07 | Embeddings + duplicate merge + aliases | Not started |  |  |  |
| T08 | Candidate finder (same subject + cross-subject, thresholds) | Not started |  |  |  |
| T09 | LLM judge: type, reason, example, strength, two snippets; reject if no evidence | Not started |  |  |  |
| T10 | Edit/delete/lock links; check locks before every write | Not started |  |  |  |
| T11 | Incremental update on new upload + graph versions + cluster hierarchy | Not started |  |  |  |
| T12 | Theory view with cross-module link chips | Not started |  |  |  |
| T13 | Chatbot: retrieval, citations, 'not in your notes', labeled fallback | Not started |  |  |  |
| T14 | Subject graph: clusters, click-to-zoom sub-graph, node/link panel | Not started |  |  |  |
| T15 | Cross-subject 3D graph + text version of cross links | Not started |  |  |  |
| T16 | Search topic -> focused graph + theory; 2D mode + auto fallback | Not started |  |  |  |
| T17 | Important concepts + repeated questions (labeled) + marks-based answers | Not started |  |  |  |
| T18 | Ghost nodes from syllabus + notes-vs-textbook preference | Not started |  |  |  |
| T19 | Run Quality Gates; fix link quality and chatbot honesty issues | Not started |  |  |  |
| T20 | Performance pass + cost/caching check; delete-all-data + consent | Not started |  |  |  |
| T21 | Pre-process demo data, cached/offline mode, 3 offline dry runs, record backup video, finalize pitch | Not started |  |  |  |

## Parked ideas
Ideas or extra work you noticed but did NOT do (scope rule). I decide later.
(none yet)

## Known issues
Bugs or weaknesses found but not fixed yet.
(none yet)

## Quality gate results
Record real numbers here after tests (see docs/QUALITY_GATES.md).
(none yet)
