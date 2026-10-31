"use client";

import { ErrorState, MembersTable, PageHeader, Panel } from "@/components/app/panels";
import { useMembers } from "@/lib/api/hooks";
import { useSession } from "@/lib/session";

export function MembersView() {
  const members = useMembers();
  const { isDemo } = useSession();
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Members"
        description={
          isDemo
            ? "People in this workspace. Invites are disabled in the demo."
            : "Invite people and change roles from the organization menu in the top bar."
        }
      />
      {members.error ? (
        <ErrorState error={members.error} />
      ) : (
        <Panel title="All members" meta={`${members.data?.length ?? "…"} total`}>
          <MembersTable members={members.data} loading={members.isPending} />
        </Panel>
      )}
      <div className="mt-6 grid gap-px border border-border bg-border sm:grid-cols-3">
        {[
          ["Owner", "Manage members, settings and billing. Approve answers."],
          ["Editor", "Upload documents, edit and approve answers."],
          ["Viewer", "Read questionnaires, answers and sources."],
        ].map(([role, body]) => (
          <div key={role} className="bg-surface-solid p-5">
            <p className="text-sm font-semibold">{role}</p>
            <p className="mt-1 text-xs text-muted-foreground">{body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
