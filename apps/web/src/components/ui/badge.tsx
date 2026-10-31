import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Answer statuses have one fixed color meaning across the product:
 * approved = green, review = amber, manual = rose, library = indigo.
 */
export type Tone = "neutral" | "primary" | "approved" | "review" | "manual" | "library";

const tones: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground",
  primary: "bg-primary/15 text-primary",
  approved: "bg-approved-bg text-approved",
  review: "bg-review-bg text-review",
  manual: "bg-manual-bg text-manual",
  library: "bg-library-bg text-library",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}
