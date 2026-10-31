"use client";

import { ErrorState, PageHeader, Panel } from "@/components/app/panels";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/lib/api/hooks";
import { readThresholds } from "@/lib/thresholds";

export function SettingsView() {
  const me = useMe();
  if (me.error) return <ErrorState error={me.error} />;
  const t = readThresholds(me.data?.org.settings);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader title="Settings" description="Organization-wide configuration." />

      <Panel title="Organization">
        <dl className="divide-y divide-border text-sm">
          <Row label="Name" value={me.data?.org.name} />
          <Row label="Organization ID" value={me.data?.org.id} mono />
          <Row label="Your role" value={me.data?.role} />
        </dl>
      </Panel>

      <Panel title="Confidence thresholds" meta={<Badge tone="neutral">Editable in Phase 3</Badge>}>
        <div className="p-5">
          <div className="relative h-2 overflow-hidden bg-muted">
            <div className="absolute inset-y-0 left-0 bg-manual" style={{ width: `${t.manual}%` }} />
            <div
              className="absolute inset-y-0 bg-review"
              style={{ left: `${t.manual}%`, width: `${t.review - t.manual}%` }}
            />
            <div className="absolute inset-y-0 right-0 bg-approved" style={{ left: `${t.review}%` }} />
          </div>
          <div className="mt-2 flex justify-between font-mono text-xs text-subtle-foreground">
            <span>0</span>
            <span>{t.manual}</span>
            <span>{t.review}</span>
            <span>100</span>
          </div>
          <ul className="mt-6 space-y-3 text-sm">
            <li className="flex gap-3">
              <Badge tone="manual">&lt; {t.manual}</Badge>
              <span className="text-muted-foreground">No answer is generated. A person writes it.</span>
            </li>
            <li className="flex gap-3">
              <Badge tone="review">
                {t.manual}–{t.review - 1}
              </Badge>
              <span className="text-muted-foreground">Drafted, flagged for careful review.</span>
            </li>
            <li className="flex gap-3">
              <Badge tone="approved">≥ {t.review}</Badge>
              <span className="text-muted-foreground">Drafted and ready to approve.</span>
            </li>
          </ul>
        </div>
      </Panel>

      <Panel title="Data handling">
        <ul className="divide-y divide-border text-sm">
          {[
            "Customer data is never used to train models.",
            "Files are encrypted at rest and served through short-lived signed links.",
            "Row-level security isolates this organization's data in the database.",
          ].map((line) => (
            <li key={line} className="flex items-center gap-3 px-5 py-3">
              <span className="text-approved">✓</span>
              {line}
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div className="grid grid-cols-3 gap-4 px-5 py-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`col-span-2 truncate ${mono ? "font-mono text-xs leading-5" : ""}`}>
        {value ?? <Skeleton className="h-4 w-40" />}
      </dd>
    </div>
  );
}
