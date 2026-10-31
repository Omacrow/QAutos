import { cn } from "@/lib/cn";

/** Score bands match the answer statuses: >=80 approved-ready, >=50 review, else manual. */
export function confidenceTone(score: number): "approved" | "review" | "manual" {
  if (score >= 80) return "approved";
  if (score >= 50) return "review";
  return "manual";
}

const fill = { approved: "bg-approved", review: "bg-review", manual: "bg-manual" } as const;
const text = { approved: "text-approved", review: "text-review", manual: "text-manual" } as const;

export function ConfidenceMeter({ score, reason }: { score: number; reason?: string }) {
  const tone = confidenceTone(score);
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-3">
        <div
          className="h-1.5 w-24 overflow-hidden rounded-full bg-muted"
          role="meter"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Confidence"
        >
          <div className={cn("h-full rounded-full", fill[tone])} style={{ width: `${clamped}%` }} />
        </div>
        <span className={cn("font-mono text-sm tabular-nums", text[tone])}>{clamped}</span>
      </div>
      {reason && <p className="mt-1 text-xs text-muted-foreground">{reason}</p>}
    </div>
  );
}
