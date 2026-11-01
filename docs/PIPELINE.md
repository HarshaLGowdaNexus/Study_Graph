# Ingestion Pipeline (14 steps)

Every uploaded file passes through these steps. Each step saves its output so a failure never forces a full reprocess.

Note: the Tool column holds early suggestions only. Real technology choices exist only in DECISIONS.md.

| Step | Name | Input | What happens | Output | Tool | Failure -> fix (risk ID) |
|---|---|---|---|---|---|---|
| 1 | Upload & store | Raw file + chosen subject/module | Save original file; create document record; queue background job. | Document row, job id | Object storage + queue | Large files or many uploads -> queue + progress bar (R07) |
| 2 | Detect type | Document | Text PDF vs scanned PDF vs PPT vs image. | Route: direct text or vision | Python | Wrong route -> try direct text first, fall back to vision |
| 3 | Extract text | Document | Direct text extraction, or vision LLM transcription page by page (keeps page numbers). | Pages with text | PDF/PPT parser + vision LLM | Bad handwriting -> review step catches it (R06) |
| 4 | Chunk & tag | Pages | Split by headings/paragraphs; keep file, page, module for citations. | Chunks with source metadata | Python | Lost citations -> store page/file on every chunk |
| 5 | Verify subject | Chunks + folder name | Classify content against folder subject; ask student if mismatch. | Confirmed subject | LLM + embeddings | Wrong subject (R15) -> ask, never silently move |
| 6 | Extract topics | Chunks | LLM returns topics: keyword, 1-4 line explanation, real-world application, source chunk ids. | Candidate topics | LLM (structured JSON output) | Hallucinated topics -> must cite source chunk ids |
| 7 | Student review | Candidate topics | Short review screen: edit, delete, or skip. | Approved topics | Web UI | Skipped -> topics marked 'unreviewed' and linked more conservatively |
| 8 | Dedupe & merge | Approved topics + existing topics | Embedding similarity + LLM confirm; keep aliases. | Merged topic set | Embeddings + LLM | Wrong merge -> student can split; merge is logged (R08) |
| 9 | Find link candidates | New topics | Top-k similar topics in same subject and across subjects using embeddings. | Candidate pairs | pgvector | Too many pairs -> cap k; stricter threshold cross-subject (R19) |
| 10 | LLM judge | Candidate pairs + source chunks | Accept/reject; if accepted return type, reason, industry example, strength 1-5, one snippet from each side. | Edges with evidence | LLM (structured JSON) | No snippet or reason -> reject automatically (R03) |
| 11 | Apply locks & rules | Edges + user edits | Skip pairs the student deleted; never overwrite locked/edited edges. | Final edges | Python | Overwritten edits -> locked flag checked before every write (R16) |
| 12 | Cluster & version | Topics + edges | Community detection builds clusters/sub-clusters; increment graph version. | Cluster tree | Graph library (networkx) | Hairball -> hierarchy + hide weak edges (R09) |
| 13 | Refresh theory cards | Changed topics only | Regenerate only cards whose links changed. | Updated theory view | LLM | Full regeneration is costly -> only diffs (R07) |
| 14 | Notify & cache | Graph version | Tell student what changed ('3 new links'); cache graph JSON for fast load/offline demo. | Cached graph JSON | Backend | Slow UI or no network on demo day (R17) |
