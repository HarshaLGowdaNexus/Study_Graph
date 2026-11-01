# Data Model

The graph is stored as nodes (topics) and edges tables inside a relational database with vector support. Do NOT change this schema without my approval.

| Table | Key fields | Purpose |
|---|---|---|
| universities | id, name | Multi-university from day 1 (F25) |
| schemes | id, university_id, name (e.g. 2022 scheme), valid_from, valid_to | Syllabus versioning (F24) |
| syllabus_subjects | id, scheme_id, code, name, semester, branch | Official subject list |
| syllabus_topics | id, syllabus_subject_id, module_no, title, parent_id | Skeleton for ghost nodes; admin editable |
| syllabus_topic_map | old_topic_id, new_topic_id, relation | Maps old scheme to new scheme when syllabus changes |
| users | id, email, name, created_at | Auth |
| subjects | id, user_id, syllabus_subject_id (nullable), name, source_preference (notes/textbook) | Student's own subject folders |
| documents | id, subject_id, module_no, filename, type, source_kind (notes/textbook/paper), status, uploaded_at | Original files |
| chunks | id, document_id, page, text, embedding | For citations and chatbot retrieval |
| topics | id, subject_id, keyword, explanation (max 4 lines), real_world_use, embedding, syllabus_topic_id (nullable), reviewed (bool), cluster_id | Graph nodes |
| topic_sources | topic_id, chunk_id | Evidence for each topic |
| topic_aliases | topic_id, alias | Merged names |
| edges | id, topic_a, topic_b, type, reason, industry_example, strength (1-5), scope (same_subject/cross_subject), status (auto/edited/deleted), locked (bool), graph_version | Graph links |
| edge_evidence | edge_id, chunk_id, snippet | Two snippets per edge; no evidence = no edge |
| clusters | id, subject_id, parent_id, label | Hierarchy for cluster zoom |
| graph_versions | id, user_id, created_at, summary | What changed on each upload |
| exam_papers | id, subject_id, year, document_id | Uploaded previous-year papers |
| exam_questions | id, paper_id, text, marks, cluster_key, topic_id | Repeated-question analysis |
| share_links | id, subject_id, token, created_at, revoked_at | Graph-only sharing (F23) |
| chat_messages | id, user_id, subject_id, role, text, citations_json, answered_from (notes/general) | Chat history with honesty label |
