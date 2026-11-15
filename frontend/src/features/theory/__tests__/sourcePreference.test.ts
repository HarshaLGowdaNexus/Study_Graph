import { describe, expect, it } from "vitest";
import { formatSourceKindLabel } from "../sourceUtils";

describe("Source Preference Helpers (Task T18B)", () => {
  it("formats source kind citation labels clearly", () => {
    expect(formatSourceKindLabel("notes")).toBe("Lecture Notes");
    expect(formatSourceKindLabel("textbook")).toBe("Textbook");
    expect(formatSourceKindLabel(null)).toBe("Study Material");
  });
});
