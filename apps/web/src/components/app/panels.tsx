"use client";

import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, type AuditEvent, type Member } from "@/lib/api/client";

export function PageHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

/** Boxed panel with a title bar, matching the marketing site's ruled look. */
export function Panel({
  title,
  meta,
  children,
  className,
}: {
  title: ReactNode;
  meta?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`border border-border bg-surface-solid ${className ?? ""}`}>
      <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {meta && <div className="text-xs text-muted-foreground">{meta}</div>}
      </div>
      {children}
    </section>
  );
}

const ROLE_TONE = { owner: "primary", editor: "library", viewer: "neutral" } as const;

export function MembersTable({ members, loading }: { members?: Member[]; loading: boolean }) {
  if (loading) return <Skeleton className="m-5 h-32" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-subtle-foreground">
            <th className="px-5 py-2.5 font-medium">Member</th>
            <th className="px-5 py-2.5 font-medium">Role</th>
            <th className="hidden px-5 py-2.5 font-medium sm:table-cell">Last seen</th>
          </tr>
        </thead>
        <tbody>
          {members?.map((m) => (
            <tr key={m.id} className="border-b border-border last:border-b-0">
              <td className="px-5 py-3">
                <div className="flex items-center gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center border border-border bg-surface-raised text-xs font-semibold text-primary">
                    {initials(m.display_name ?? m.email ?? m.clerk_user_id)}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {m.display_name ?? m.clerk_user_id}
                    </span>
                    {m.email && (
                      <span className="block truncate text-xs text-muted-foreground">{m.email}</span>
                    )}
                  </span>
                </div>
              </td>
              <td className="px-5 py-3">
                <Badge tone={ROLE_TONE[m.role]}>{m.role}</Badge>
              </td>
              <td className="hidden px-5 py-3 text-muted-foreground sm:table-cell">
                {formatRelative(m.last_seen_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const ACTION_LABELS: Record<string, string> = {
  "membership.upserted": "Member added or updated",
  "membership.deleted": "Member removed",
  "settings.updated": "Settings changed",
  "org.deleted": "Organization deleted",
  "document.uploaded": "Document uploaded",
  "document.processed": "Document indexed",
  "document.failed": "Document processing failed",
  "document.downloaded": "Document downloaded",
  "document.reprocessed": "Document reprocessing requested",
  "document.deleted": "Document deleted",
};

export function AuditList({ events, loading }: { events?: AuditEvent[]; loading: boolean }) {
  if (loading) return <Skeleton className="m-5 h-32" />;
  if (!events?.length) return <p className="px-5 py-8 text-sm text-muted-foreground">No events yet.</p>;
  return (
    <ol>
      {events.map((e) => (
        <li
          key={e.id}
          className="grid grid-cols-[auto_1fr] gap-x-4 border-b border-border px-5 py-3 text-sm last:border-b-0"
        >
          <span className="mt-1.5 size-1.5 rounded-full bg-primary" />
          <div className="min-w-0">
            <p>{ACTION_LABELS[e.action] ?? e.action}</p>
            <p className="mt-0.5 truncate font-mono text-xs text-subtle-foreground">
              {formatRelative(e.created_at)} · by {e.actor_clerk_user_id ?? "system"}
              {e.target_id ? ` · ${e.target_id}` : ""}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ErrorState({ error }: { error: Error }) {
  const message =
    error instanceof ApiError && error.status === 403
      ? "You don't have access to this."
      : error instanceof ApiError && error.status === 401
        ? "Your session expired. Sign in again."
        : "Couldn't reach the API. Check that it's running and NEXT_PUBLIC_API_URL is set.";
  return (
    <div className="border border-dashed border-manual/40 bg-manual-bg p-6 text-sm">
      <p className="font-medium text-manual">Something went wrong</p>
      <p className="mt-1 text-muted-foreground">{message}</p>
    </div>
  );
}

function initials(name: string): string {
  return name
    .replace(/^demo:/, "")
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export function formatRelative(iso: string, now = Date.now()): string {
  const seconds = Math.round((now - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}
