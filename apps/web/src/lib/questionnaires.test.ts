import { describe, expect, it } from "vitest";

import {
  columnName,
  locatorLabel,
  precheckQuestionnaire,
  questionnaireError,
} from "./questionnaires";

describe("locatorLabel", () => {
  it("describes spreadsheet cells", () => {
    expect(locatorLabel({ sheet: "CAIQ", row: 12, answer_cell: "C12" })).toBe(
      "CAIQ · row 12 · answer C12",
    );
  });
  it("describes pages, tables and paragraphs", () => {
    expect(locatorLabel({ page: 3 })).toBe("p.3");
    expect(locatorLabel({ table: 1, row: 4, answer_col: 2 })).toBe("Table 1 · row 4");
    expect(locatorLabel({ paragraph: 0 })).toBe("¶1");
    expect(locatorLabel({})).toBe("");
  });
});

describe("columnName", () => {
  it.each([
    [0, "A"],
    [25, "Z"],
    [26, "AA"],
    [701, "ZZ"],
  ])("%i -> %s", (index, name) => {
    expect(columnName(index)).toBe(name);
  });
});

describe("questionnaire helpers", () => {
  it("accepts every supported format", () => {
    for (const name of ["a.xlsx", "a.CSV", "a.docx", "a.pdf", "a.xml", "a.png", "a.jpeg"]) {
      expect(precheckQuestionnaire({ name, size: 10 })).toBeNull();
    }
    expect(precheckQuestionnaire({ name: "a.txt", size: 10 })).toMatch(/Supported/);
  });
  it("explains failures", () => {
    expect(questionnaireError("no_questions")).toMatch(/No questions/);
    expect(questionnaireError("weird")).toBe("Import failed.");
  });
});
