import { Badge } from "@/components/ui/badge";
import type { DocumentInfo } from "@/lib/api/client";
import { isPending, STATUS_TONE } from "@/lib/documents";

const LABELS = { queued: "Queued", processing: "Processing", ready: "Indexed", failed: "Failed" };

export function StatusBadge({ doc }: { doc: Pick<DocumentInfo, "status"> }) {
  return (
    <Badge tone={STATUS_TONE[doc.status]}>
      {isPending(doc) && <Spinner />}
      {LABELS[doc.status]}
    </Badge>
  );
}

export function Spinner() {
  return (
    <span
      className="size-2.5 animate-spin rounded-full border border-current border-t-transparent"
      aria-hidden
    />
  );
}
