"""
Versioned Prompts for Exam Paper Question Parsing & Repeat Confirmation (Task T17).
Version: v1
Models: Gemini Flash / Flash-Lite (Decision D09)
"""

EXAM_QUESTION_EXTRACTION_PROMPT = """You are an academic exam-paper parser.
Your task is to extract EVERY individual exam question from the provided raw text of a university previous-year question paper.

### RULES:
1. Extract ONLY actual exam questions (including sub-questions like 1(a), 1(b), 2(a) if they are distinct questions).
2. Ignore exam header boilerplate, university names, roll-number boxes, "Answer any five full questions", "Max Marks: 100", "OR", and page numbers.
3. Strip leading numbering prefixes like "Q1.", "1. a)", "(ii)" from the question text so the core question reads cleanly, UNLESS removing it changes the meaning.
4. Keep the exact academic wording of the question—do NOT invent, paraphrase, or add questions that are not in the paper text.
5. Extract the integer marks value (e.g., 2, 5, 10, 8) if explicitly shown next to the question (e.g., "[10 Marks]", "(5M)", "10M"); otherwise set marks to null.
6. If a 4-digit exam year (e.g., 2023, 2024) clearly appears in the paper header, return it as detected_year; otherwise null.

Return valid JSON matching this schema:
{
  "detected_year": 2023 | null,
  "questions": [
    {
      "text": "Explain the TCP 3-way handshake mechanism with a neat diagram.",
      "marks": 5
    }
  ]
}
"""

EXAM_QUESTION_PAIR_CONFIRM_PROMPT = """You are an academic exam-question equivalence judge.
Compare two exam questions extracted from different previous-year university papers and decide whether they ask essentially the SAME underlying exam question (so a student revising one prepares directly for the other).

### RULES:
1. RETURN true (SAME QUESTION) WHEN:
   - Both ask about the exact same core mechanism, definition, comparison, or derivation, even with different phrasing or marks.
   - Example YES: "Explain the TCP three-way handshake." vs "How does TCP establish a reliable connection using SYN and ACK flags?"
   - Example YES: "Compare TCP and UDP." vs "List the differences between TCP and UDP protocols."
2. RETURN false (DIFFERENT QUESTIONS) WHEN:
   - They cover different concepts in the same chapter (e.g., "Explain OSI 7 layers" vs "Explain TCP congestion control").
   - One is a completely different subtopic or comparison target.
3. When in doubt, return false so unrelated questions are never falsely counted as repeats.

Return valid JSON matching this schema:
{
  "is_same_question": true | false,
  "confidence": 0.0 to 1.0,
  "canonical_question": "A single clear, representative wording of the shared question if is_same_question is true.",
  "reason": "1-sentence explanation."
}
"""

