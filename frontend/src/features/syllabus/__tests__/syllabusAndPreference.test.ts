import { describe, expect, it } from "vitest";
import {
  computeCoverageStats,
  formatSourceKindLabel,
  isGhostNode,
  SyllabusTopicItem,
} from "../syllabusUtils";

describe("Syllabus Ghost Nodes & Source Preference Helpers (T18)", () => {
  it("detects ghost nodes from either is_ghost flag or ghost: prefix", () => {
    expect(isGhostNode({ id: "ghost:123", is_ghost: true })).toBe(true);
    expect(isGhostNode({ id: "ghost:abc" })).toBe(true);
    expect(isGhostNode({ id: "11111111-1111-1111-1111-111111111111", is_ghost: false })).toBe(false);
  });

  it("formats source kind citation labels clearly", () => {
    expect(formatSourceKindLabel("notes")).toBe("Lecture Notes");
    expect(formatSourceKindLabel("textbook")).toBe("Textbook");
    expect(formatSourceKindLabel(null)).toBe("Study Material");
  });

  it("computes syllabus coverage and gaps accurately", () => {
    const items: SyllabusTopicItem[] = [
      {
        id: "s1",
        syllabus_subject_id: "sub1",
        module_no: 1,
        title: "Process States",
        reviewed: true,
        is_covered: true,
        matched_topics: [],
      },
      {
        id: "s2",
        syllabus_subject_id: "sub1",
        module_no: 1,
        title: "CPU Scheduling",
        reviewed: true,
        is_covered: false,
        matched_topics: [],
      },
      {
        id: "s3",
        syllabus_subject_id: "sub1",
        module_no: 2,
        title: "Deadlocks",
        reviewed: false,
        is_covered: false,
        matched_topics: [],
      },
    ];

    const stats = computeCoverageStats(items);
    expect(stats.total).toBe(3);
    expect(stats.covered).toBe(1);
    expect(stats.gaps).toBe(2);
    expect(stats.percent).toBe(33.3);
  });
});

