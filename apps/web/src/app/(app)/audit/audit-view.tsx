"use client";

import { AuditList, ErrorState, PageHeader, Panel } from "@/components/app/panels";
import { hasRole } from "@/lib/api/client";
import { useAuditEvents, useMe } from "@/lib/api/hooks";

export function AuditView() {
  const me = useMe();
  const isOwner = hasRole(me.data?.role, "owner");
  const audit = useAuditEvents(isOwner, 100);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Audit log"
        description="Append-only. Records who did what and when; never the content of documents or answers."
      />
      {me.data && !isOwner ? (
        <p className="text-sm text-muted-foreground">Only owners can view the audit log.</p>
      ) : audit.error ? (
        <ErrorState error={audit.error} />
      ) : (
        <Panel title="Events" meta={`Latest ${audit.data?.length ?? "…"}`}>
          <AuditList events={audit.data} loading={audit.isPending || me.isPending} />
        </Panel>
      )}
    </div>
  );
}
