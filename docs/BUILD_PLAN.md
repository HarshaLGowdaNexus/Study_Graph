# Build Plan (21 tasks, strictly in order)

T-IDs are tasks. I give you one T-ID at a time. Details for each task are in the prompt I paste; this file is the master list.

| ID | Phase | Task | Duration (days) | Features | Risks handled |
|---|---|---|---|---|---|
| T01 | 0 Setup | Create repo, database and storage project, schema (Data Model sheet), API keys | 2 | - | R18 |
| T02 | 0 Setup | Collect REAL data: 2-3 subjects of class notes (typed + scanned), 1 textbook, 3+ previous-year papers | 2 | F01 | R02,R05 |
| T03 | 1 Pipeline | Upload + folder structure + storage + job queue with progress | 3 | F01 | R07 |
| T04 | 1 Pipeline | Text extraction + vision OCR with page numbers | 3 | F02 | R06 |
| T05 | 1 Pipeline | Topic extraction (keyword, 1-4 lines, real-world use, source chunks) | 3 | F04 | R03 |
| T06 | 1 Pipeline | Review screen (skippable) | 2 | F03 | R06 |
| T07 | 1 Pipeline | Embeddings + duplicate merge + aliases | 3 | F05 | R08 |
| T08 | 2 Linking | Candidate finder (same subject + cross-subject, thresholds) | 3 | F06 | R19 |
| T09 | 2 Linking | LLM judge: type, reason, example, strength, two snippets; reject if no evidence | 4 | F06,F07 | R03 |
| T10 | 2 Linking | Edit/delete/lock links; check locks before every write | 2 | F08 | R16 |
| T11 | 2 Linking | Incremental update on new upload + graph versions + cluster hierarchy | 3 | F09 | R07,R09 |
| T12 | 3 Theory + Chat | Theory view with cross-module link chips | 3 | F10 | R04 |
| T13 | 3 Theory + Chat | Chatbot: retrieval, citations, 'not in your notes', labeled fallback | 4 | F14 | R10 |
| T14 | 4 Graph UI | Subject graph: clusters, click-to-zoom sub-graph, node/link panel | 5 | F11 | R09,R14 |
| T15 | 4 Graph UI | Cross-subject 3D graph + text version of cross links | 4 | F12 | R14,R19 |
| T16 | 4 Graph UI | Search topic -> focused graph + theory; 2D mode + auto fallback | 3 | F13,F15 | R14 |
| T17 | 5 Exam + Extras | Important concepts + repeated questions (labeled) + marks-based answers | 3 | F18,F19,F20 | R05 |
| T18 | 5 Exam + Extras | Ghost nodes from syllabus + notes-vs-textbook preference | 3 | F16,F17 | R13 |
| T19 | 6 Hardening | Run Quality Gates; fix link quality and chatbot honesty issues | 3 | F06,F14 | R03,R10 |
| T20 | 6 Hardening | Performance pass + cost/caching check; delete-all-data + consent | 2 | F22 | R07,R11,R14 |
| T21 | 6 Hardening | Pre-process demo data, cached/offline mode, 3 offline dry runs, record backup video, finalize pitch | 3 | - | R01,R17 |
