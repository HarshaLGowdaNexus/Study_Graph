import { describe, expect, it } from "vitest";
import {
  IMPORTANT_CONCEPTS_LABEL,
  REPEATED_QUESTIONS_LABEL,
  formatPaperFrequencyLabel,
  getMarksDescription,
  getRepeatedQuestionsEmptyNotice,
} from "../examModeUtils";

describe("Exam Mode honesty & formatting helpers (T17)", () => {
  it("keeps exact honest provenance labels for concepts and repeated questions", () => {
    expect(IMPORTANT_CONCEPTS_LABEL).toBe("by graph importance");
    expect(REPEATED_QUESTIONS_LABEL).toBe("from your uploaded papers");
  });

  it("shows an honest non-fabricated message when zero papers exist (Risk R05)", () => {
    const notice = getRepeatedQuestionsEmptyNotice(0, 0);
    expect(notice).not.toBeNull();
    expect(notice!.toLowerCase()).toContain("no previous-year papers uploaded");
    expect(notice!.toLowerCase()).toContain("never invent");
  });

  it("formats distinct paper repeat counts accurately", () => {
    expect(formatPaperFrequencyLabel(3, 3)).toBe("Repeated in 3 of 3 papers");
    expect(formatPaperFrequencyLabel(1, 3)).toBe("Appears in 1 of 3 papers");
    expect(formatPaperFrequencyLabel(1, 1)).toBe("Appears in 1 of 1 paper");
  });

  it("describes 2, 5, and 10 marks answer formats distinctly", () => {
    expect(getMarksDescription(2)).toContain("1-2");
    expect(getMarksDescription(5)).toContain("bullet");
    expect(getMarksDescription(10)).toContain("headings");
  });
});

