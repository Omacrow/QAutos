import { describe, expect, it } from "vitest";

import { formatCitation } from "./citation-chip";
import { confidenceTone } from "./confidence-meter";

describe("formatCitation", () => {
  it("includes page and heading when present", () => {
    expect(formatCitation({ documentName: "Encryption Policy", page: 3, heading: "2.1" })).toBe(
      "Encryption Policy · p.3 · §2.1",
    );
  });
  it("shows page ranges", () => {
    expect(formatCitation({ documentName: "Policy", page: 4, pageEnd: 5, heading: null })).toBe(
      "Policy · p.4–5",
    );
  });
  it("cites spreadsheet rows instead of pages", () => {
    expect(
      formatCitation({
        documentName: "Answers.xlsx",
        page: null,
        sheet: "CAIQ",
        heading: "CAIQ",
        rowStart: 2,
        rowEnd: 4,
      }),
    ).toBe("Answers.xlsx · CAIQ · rows 2–4");
    expect(
      formatCitation({ documentName: "A.xlsx", page: null, sheet: "S", rowStart: 7, rowEnd: 7 }),
    ).toBe("A.xlsx · S · row 7");
  });
  it("omits missing parts", () => {
    expect(formatCitation({ documentName: "Past CAIQ.xlsx", page: null })).toBe("Past CAIQ.xlsx");
  });
});

describe("confidenceTone", () => {
  it.each([
    [95, "approved"],
    [80, "approved"],
    [79, "review"],
    [50, "review"],
    [49, "manual"],
  ] as const)("%i -> %s", (score, tone) => {
    expect(confidenceTone(score)).toBe(tone);
  });
});
