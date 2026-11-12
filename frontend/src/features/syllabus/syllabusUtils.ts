export interface MatchedTopicSummary {
  topic_id: string;
  keyword: string;
  module_no?: number | null;
  syllabus_match_locked: boolean;
}

export interface SyllabusTopicItem {
  id: string;
  syllabus_subject_id: string;
  module_no: number;
  title: string;
  parent_id?: string | null;
  reviewed: boolean;
  is_covered: boolean;
  matched_topics: MatchedTopicSummary[];
}

export interface ModuleCoverageItem {
  module_no: number;
  total_topics: number;
  covered_count: number;
  gap_count: number;
  coverage_percent: number;
  covered_titles: string[];
  gap_topics: SyllabusTopicItem[];
}

export interface SyllabusMetadata {
  syllabus_subject_id?: string | null;
  university_id?: string | null;
  university_name?: string | null;
  scheme_id?: string | null;
  scheme_name?: string | null;
  subject_code?: string | null;
  semester?: number | null;
  branch?: string | null;
}

export interface SubjectSyllabusResponse {
  subject_id: string;
  subject_name: string;
  source_preference: "notes" | "textbook";
  has_syllabus: boolean;
  metadata?: SyllabusMetadata | null;
  total_syllabus_topics: number;
  covered_count: number;
  gap_count: number;
  coverage_percent: number;
  unreviewed_count: number;
  syllabus_topics: SyllabusTopicItem[];
  modules: ModuleCoverageItem[];
  gaps: SyllabusTopicItem[];
}

export function isGhostNode(node: { is_ghost?: boolean; id?: string }): boolean {
  return Boolean(node.is_ghost) || (typeof node.id === "string" && node.id.startsWith("ghost:"));
}

export function formatSourceKindLabel(sourceKind?: string | null): string {
  if (sourceKind === "textbook") return "Textbook";
  if (sourceKind === "notes") return "Lecture Notes";
  return "Study Material";
}

export function computeCoverageStats(topics: SyllabusTopicItem[]): {
  total: number;
  covered: number;
  gaps: number;
  percent: number;
} {
  const total = topics.length;
  const covered = topics.filter((t) => t.is_covered).length;
  const gaps = total - covered;
  const percent = total > 0 ? Math.round((covered / total) * 1000) / 10 : 0;
  return { total, covered, gaps, percent };
}

