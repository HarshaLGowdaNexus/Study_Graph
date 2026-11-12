/**
 * Pure formatting and honesty helpers for Exam Mode (Task T17).
 * Relies on Features F18, F19, F20 and Risks R05, R10.
 */

export type ExamMarks = 2 | 5 | 10;

export const IMPORTANT_CONCEPTS_LABEL = "by graph importance";
export const REPEATED_QUESTIONS_LABEL = "from your uploaded papers";

export function getRepeatedQuestionsEmptyNotice(totalPapers: number, totalQuestions: number): string | null {
  if (totalPapers === 0) {
    return (
      "No previous-year papers uploaded yet for this subject. " +
      "Upload past question papers to detect repeated questions — we never invent or guess exam repeats."
    );
  }
  if (totalQuestions === 0) {
    return `Uploaded ${totalPapers} paper(s), waiting for question extraction to complete.`;
  }
  return null;
}

export function formatPaperFrequencyLabel(repeatCount: number, totalPapers: number): string {
  const safeTotal = Math.max(repeatCount, totalPapers);
  if (repeatCount >= 2) {
    return `Repeated in ${repeatCount} of ${safeTotal} papers`;
  }
  return `Appears in ${repeatCount} of ${safeTotal} ${safeTotal === 1 ? "paper" : "papers"}`;
}

export function getMarksDescription(marks: ExamMarks | null): string {
  if (marks === 2) return "1-2 crisp lines";
  if (marks === 5) return "Short structured bullet points";
  if (marks === 10) return "Detailed structured headings";
  return "Standard grounded answer";
}

