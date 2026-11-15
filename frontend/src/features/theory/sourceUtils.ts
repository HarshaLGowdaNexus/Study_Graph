/**
 * Utility functions for Source Preference (Lecture Notes vs. Textbook).
 * Relies on Feature F17: Source provenance and preference.
 */

export function formatSourceKindLabel(sourceKind?: string | null): string {
  if (sourceKind === "textbook") return "Textbook";
  if (sourceKind === "notes") return "Lecture Notes";
  return "Study Material";
}
