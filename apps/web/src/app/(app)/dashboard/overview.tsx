"use client";

import { OrganizationList } from "@clerk/nextjs";
import Link from "next/link";

import { ConfidenceMeter } from "@/components/answer/confidence-meter";
import { AuditList, ErrorState, MembersTable, PageHeader, Panel } from "@/components/app/panels";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { hasRole } from "@/lib/api/client";
import {
  useAuditEvents,
  useDocuments,
  useMe,
  useMembers,
  useQuestionnaires,
} from "@/lib/api/hooks";
import { useSession } from "@/lib/session";
import { readThresholds } from "@/lib/thresholds";

export function Overview() {
  const { isLoaded, orgKey, isDemo } = useSession();

  if (isLoaded && !orgKey && !isDemo) {
    return (
      <div className="mx-auto max-w-lg pt-12 text-center">
        <h1 className="text-2xl font-semibold">Choose an organization</h1>
        <p className="mt-2 mb-8 text-muted-foreground">
          All documents and answers belong to an organization. Create one or pick an existing one.
        </p>
        <OrganizationList hidePersonal afterSelectOrganizationUrl="/dashboard" />
      </div>
    );
  }
  return <OrgOverview />;
}

// Shown for features from later phases, clearly marked as sample data.
const PIPELINE_PREVIEW = [
  { name: "Globex — Vendor Security Assessment", format: "XLSX", total: 212, approved: 168, review: 31, manual: 13 },
  { name: "Initech — CAIQ v4.0.3", format: "XLSX", total: 261, approved: 240, review: 15, manual: 6 },
  { name: "Acme Health — HECVAT Lite", format: "DOCX", total: 98, approved: 52, review: 30, manual: 16 },
];

function OrgOverview() {
  const me = useMe();
  const members = useMembers();
  const documents = useDocuments();
  const indexed = documents.data?.filter((d) => d.status === "ready").length ?? 0;
  const questionnaires = useQuestionnaires();
  const isOwner = hasRole(me.data?.role, "owner");
  const audit = useAuditEvents(isOwner, 6);

  if (me.error) return <ErrorState error={me.error} />;
  const thresholds = readThresholds(me.data?.org.settings);

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={me.data ? me.data.org.name : <Skeleton className="h-9 w-64" />}
        description={
          <>
            Signed in as <span className="font-medium text-foreground">{me.data?.role ?? "…"}</span>
          </>
        }
      />

      {/* KPI row: real counts from the API; later phases fill in the rest */}
      <div className="grid gap-px border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Members" value={members.data?.length} loading={members.isPending} />
        <Kpi
          label="Documents indexed"
          value={indexed}
          loading={documents.isPending}
          href="/documents"
        />
        <Kpi
          label="Questionnaires"
          value={questionnaires.data?.length}
          loading={questionnaires.isPending}
          href="/questionnaires"
        />
        <Kpi label="Library answers" value={0} hint="Ships in Phase 4" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Panel
          title="Questionnaire pipeline"
          meta={<Badge tone="neutral">Preview · sample data</Badge>}
        >
          <ul>
            {PIPELINE_PREVIEW.map((q) => (
              <li key={q.name} className="border-b border-border px-5 py-4 last:border-b-0">
                <div className="flex items-center justify-between gap-4">
                  <p className="truncate text-sm font-medium">{q.name}</p>
                  <span className="shrink-0 border border-border px-1.5 font-mono text-[10px] text-muted-foreground">
                    {q.format}
                  </span>
                </div>
                <div className="mt-3 flex h-1.5 overflow-hidden bg-muted">
                  <div className="bg-approved" style={{ width: `${(q.approved / q.total) * 100}%` }} />
                  <div className="bg-review" style={{ width: `${(q.review / q.total) * 100}%` }} />
                  <div className="bg-manual" style={{ width: `${(q.manual / q.total) * 100}%` }} />
                </div>
                <p className="mt-2 font-mono text-xs text-muted-foreground">
                  <span className="text-approved">{q.approved} ready</span> ·{" "}
                  <span className="text-review">{q.review} review</span> ·{" "}
                  <span className="text-manual">{q.manual} manual</span> · {q.total} total
                </p>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Confidence thresholds" meta={<Link href="/settings" className="hover:text-foreground">Settings →</Link>}>
          <div className="space-y-4 p-5 text-sm">
            <Threshold label="Ready to approve" min={thresholds.review} tone="approved" />
            <Threshold label="Needs review" min={thresholds.manual} tone="review" />
            <div className="flex items-center justify-between">
              <Badge tone="manual">Needs manual answer</Badge>
              <span className="font-mono text-xs text-muted-foreground">&lt; {thresholds.manual}</span>
            </div>
            <p className="border-t border-border pt-4 text-xs text-muted-foreground">
              Below the manual threshold, no answer is generated. Example score:
            </p>
            <ConfidenceMeter score={86} reason="3/3 claims supported · strong rerank" />
          </div>
        </Panel>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Panel title="Team" meta={<Link href="/members" className="hover:text-foreground">All members →</Link>}>
          <MembersTable members={members.data?.slice(0, 5)} loading={members.isPending} />
        </Panel>
        {isOwner && (
          <Panel title="Recent activity" meta={<Link href="/audit" className="hover:text-foreground">Audit log →</Link>}>
            <AuditList events={audit.data} loading={audit.isPending} />
          </Panel>
        )}
      </div>

      <Panel title="Getting started" className="mt-6">
        <ol className="grid gap-px bg-border sm:grid-cols-3">
          {(
            [
              ["Invite your team", "Owners, editors and viewers.", true, null],
              [
                "Upload security documents",
                "Policies, SOC 2 reports, past questionnaires.",
                indexed > 0,
                "/documents",
              ],
              [
                "Import a questionnaire",
                "Any format, including scans and photos.",
                Boolean(questionnaires.data?.length),
                "/questionnaires",
              ],
            ] as const
          ).map(([title, body, done, href], i) => (
            <li key={title} className="bg-surface-solid p-5">
              <p className={`font-mono text-xs ${done ? "text-approved" : "text-primary"}`}>
                {done ? "✓ done" : `step 0${i + 1}`}
              </p>
              {href ? (
                <Link href={href} className="mt-2 block text-sm font-medium hover:text-primary">
                  {title} →
                </Link>
              ) : (
                <p className="mt-2 text-sm font-medium">{title}</p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">{body}</p>
            </li>
          ))}
        </ol>
      </Panel>
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
  loading = false,
  href,
}: {
  label: string;
  value?: number;
  hint?: string;
  loading?: boolean;
  href?: string;
}) {
  return (
    <div className="relative bg-surface-solid p-5">
      <p className="text-xs text-muted-foreground">
        {href ? (
          <Link href={href} className="after:absolute after:inset-0 hover:text-foreground">
            {label} →
          </Link>
        ) : (
          label
        )}
      </p>
      {loading ? (
        <Skeleton className="mt-3 h-8 w-12" />
      ) : (
        <p className="mt-2 text-3xl font-semibold tabular-nums">{value ?? 0}</p>
      )}
      {hint && <p className="mt-1 text-xs text-subtle-foreground">{hint}</p>}
    </div>
  );
}

function Threshold({ label, min, tone }: { label: string; min: number; tone: "approved" | "review" }) {
  return (
    <div className="flex items-center justify-between">
      <Badge tone={tone}>{label}</Badge>
      <span className="font-mono text-xs text-muted-foreground">≥ {min}</span>
    </div>
  );
}
