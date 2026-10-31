import { describe, expect, it } from "vitest";

import { errorMessage, formatBytes, isPending, precheckFile } from "./documents";

describe("formatBytes", () => {
  it.each([
    [512, "512 B"],
    [2048, "2.0 KB"],
    [5 * 1024 * 1024, "5.0 MB"],
    [42 * 1024 * 1024, "42 MB"],
  ])("%i -> %s", (bytes, label) => {
    expect(formatBytes(bytes)).toBe(label);
  });
});

describe("precheckFile", () => {
  it("accepts supported types regardless of case", () => {
    expect(precheckFile({ name: "Policy.PDF", size: 10 })).toBeNull();
    expect(precheckFile({ name: "a.xlsx", size: 10 })).toBeNull();
  });
  it("rejects other types, empty and oversized files", () => {
    expect(precheckFile({ name: "a.txt", size: 10 })).toMatch(/Only PDF/);
    expect(precheckFile({ name: "a.docm", size: 10 })).toMatch(/Only PDF/);
    expect(precheckFile({ name: "a.pdf", size: 0 })).toMatch(/empty/);
    expect(precheckFile({ name: "a.pdf", size: 51 * 1024 * 1024 })).toMatch(/Larger/);
  });
});

describe("document status helpers", () => {
  it("knows which statuses are still processing", () => {
    expect(isPending({ status: "queued" })).toBe(true);
    expect(isPending({ status: "processing" })).toBe(true);
    expect(isPending({ status: "ready" })).toBe(false);
  });
  it("explains failures without leaking internals", () => {
    expect(errorMessage("no_text")).toMatch(/OCR/);
    expect(errorMessage("something_new")).toBe("Processing failed.");
    expect(errorMessage(null)).toBe("Processing failed.");
  });
});
