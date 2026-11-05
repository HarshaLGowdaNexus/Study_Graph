# Sample Data & Benchmark Ground Truth

This folder stores the **real study materials** used to test and validate StudyGraph's AI pipeline, as well as the benchmark test sets needed for our **Quality Gates**.

---

## 1. Directory Structure

```
sample-data/
├── computer_networks/
│   ├── module_1/           <- Handouts, handwritten notes, slides for Module 1
│   └── module_2/           <- Handouts, handwritten notes, slides for Module 2
├── operating_systems/
│   ├── module_1/           <- Handouts, handwritten notes, slides for Module 1
│   └── module_2/           <- Handouts, handwritten notes, slides for Module 2
├── database_management/
│   └── module_1/           <- Optional 3rd subject for cross-subject linking
├── papers/                 <- Previous-year university exam question papers
├── manifest.csv            <- Inventory of all files to ingest
├── test_questions.csv      <- 30 questions for Chatbot Quality Gates G04 & G05
├── link_labels.csv         <- 50-link human evaluation sheet for Quality Gate G01
└── README.md               <- This guide
```

---

## 2. What Real Data to Collect

1. **Subjects with Conceptual Overlap**:
   - Collect notes for **Computer Networks (CN)** and **Operating Systems (OS)** (or **DBMS**).
   - These subjects naturally share bridge concepts (e.g., Sockets, Buffers, Processes, File Descriptors, Deadlocks), providing realistic testing ground for our cross-subject knowledge graph.
2. **Document Variety**:
   - **Typed PDFs**: Clean lecture handouts or exported slides.
   - **Scanned / Photographed Notes**: 5–10 real handwritten pages (clean to messy, including at least one hand-drawn diagram). This tests Gemini Flash vision OCR (Quality Gate G03).
   - **Slides (Optional)**: 1 `.pptx` presentation.
3. **1 Reference Textbook Chapter/PDF**:
   - E.g., Tanenbaum or Kurose & Ross for Networks, or Silberschatz for Operating Systems.
4. **At least 3 Previous-Year University Exam Papers**:
   - Save these into `sample-data/papers/` to test our repeated-question and exam-mode extractor (Quality Gate G19 / Feature F19).
5. **No Synthetic / Fake Notes**:
   - Do **not** generate notes using AI. Real handwriting, irregular formatting, professor abbreviations, and textbook layouts are essential to prove our pipeline works in the real world.

---

## 3. The 3 CSV Templates

### `manifest.csv`
Every file you put in `sample-data/` must be registered here.
- **Columns**: `file_name,subject,module,type,notes`
- **Allowed Types**: `typed-pdf`, `scanned`, `ppt`, `image`, `textbook`, `paper`

### `test_questions.csv`
Used to automatically grade chatbot retrieval and honesty.
- **Rows 1–20 (`in-notes`)**: Questions answerable directly from your notes, with the exact file and page number. Feeds **Gate G04** (target: $\ge 90\%$ correct citations).
- **Rows 21–30 (`out-of-notes`)**: Questions deliberately outside your syllabus. The chatbot must flag these as *"Not found in your notes"*. Feeds **Gate G05** (target: $\ge 90\%$ correct fallback).

### `link_labels.csv`
Used for human faculty/senior review of AI-discovered topic connections.
- **50 rows**: Feeds **Gate G01** (target: $\ge 85\%$ link precision agreed by a subject matter expert).

---

## 4. How to Verify Your Collection

Run the checker script from the repository root:
```powershell
python scripts/check_sample_data.py
```

The checker will:
1. Verify that every file listed in `manifest.csv` actually exists on disk in its proper folder.
2. Alert you if there are extra/untracked files placed on disk.
3. Check for unsupported file formats.
4. Report your progress toward meeting the Quality Gate data requirements (at least 2 subjects, scanned pages, textbook, and 3+ question papers).

