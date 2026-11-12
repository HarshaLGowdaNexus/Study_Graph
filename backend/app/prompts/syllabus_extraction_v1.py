"""
Versioned Prompts for Syllabus Parsing and Ghost-Node Matching (Task T18, Decision D09).
"""

SYLLABUS_EXTRACTION_PROMPT = """You are an academic curriculum parser for StudyGraph.
Extract the official syllabus topics from the provided university syllabus text.

Rules:
1. Group every topic under its integer `module_no` (e.g. Module 1 -> 1, Unit II -> 2). If no module number is given, use 1.
2. Keep each `title` concise, clean, and atomic (one concept or sub-topic per item, e.g., "Process States and PCB", "Deadlock Prevention", "B+ Trees").
3. Split comma-separated or semicolon-separated lists in a syllabus into individual topic items so each can become a distinct ghost node on the student's knowledge graph.
4. Ignore administrative boilerplate (course objectives, grading rubrics, textbook ISBNs, exam mark schemes, faculty names).
5. Preserve the original technical terminology from the syllabus.

Syllabus Text:
\"\"\"
{syllabus_text}
\"\"\"
"""

SYLLABUS_MATCH_CONFIRM_PROMPT = """You are verifying whether a student's extracted note topic covers an official syllabus topic.

Note Topic:
- Keyword: {topic_keyword}
- Explanation: {topic_explanation}
- Module: {topic_module_no}

Candidate Official Syllabus Topic:
- Title: {syllabus_title}
- Module: {syllabus_module_no}

Question: Does the student's note topic substantially cover, define, or represent this syllabus topic (including standard synonyms, abbreviations, or sub-concepts)?
Return JSON with `is_match` (boolean), `confidence` (0.0 to 1.0), and a short `reason`.
"""

