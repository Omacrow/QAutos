import { describe, expect, it } from "vitest";

import { formatRelative } from "@/components/app/panels";

import { readThresholds } from "./thresholds";

describe("readThresholds", () => {
  it("reads org settings", () => {
    expect(readThresholds({ confidence: { manual_threshold: 40, review_threshold: 85 } })).toEqual({
      manual: 40,
      review: 85,
    });
  });
  it("falls back to defaults on missing or malformed values", () => {
    expect(readThresholds(undefined)).toEqual({ manual: 50, review: 80 });
    expect(readThresholds({ confidence: { manual_threshold: "x" } })).toEqual({ manual: 50, review: 80 });
  });
});

describe("formatRelative", () => {
  const now = Date.parse("2026-10-29T12:00:00Z");
  it.each([
    ["2026-10-29T11:59:30Z", "just now"],
    ["2026-10-29T11:45:00Z", "15m ago"],
    ["2026-10-29T09:00:00Z", "3h ago"],
    ["2026-10-21T12:00:00Z", "8d ago"],
  ])("%s -> %s", (iso, expected) => {
    expect(formatRelative(iso, now)).toBe(expected);
  });
});
