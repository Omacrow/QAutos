export type Thresholds = { manual: number; review: number };

/** Read per-org confidence thresholds from org settings, with defaults. */
export function readThresholds(settings: Record<string, unknown> | undefined): Thresholds {
  const confidence = (settings?.confidence ?? {}) as Record<string, unknown>;
  const num = (v: unknown, fallback: number) => (typeof v === "number" ? v : fallback);
  return {
    manual: num(confidence.manual_threshold, 50),
    review: num(confidence.review_threshold, 80),
  };
}
