"use client";

import Link from "next/link";

import { ErrorState, formatRelative, PageHeader, Panel } from "@/components/app/panels";
import { Uploader } from "@/components/app/uploader";
import { Spinner } from "@/components/app/document-status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { hasRole, type Questionnaire } from "@/lib/api/client";
import {
  useDeleteQuestionnaire,
  useMe,
  useQuestionnaires,
  useUploadQuestionnaire,
} from "@/lib/api/hooks";
import { formatBytes, MAX_UPLOAD_BYTES } from "@/lib/documents";
import {
  isQuestionnairePending,
  precheckQuestionnaire,
  QUESTIONNAIRE_EXTENSIONS,
  QUESTIONNAIRE_STATUS,
  questionnaireError,
} from "@/lib/questionnaires";

const KIND_LABEL: Record<string, string> = {
  xlsx: "XLSX",
  csv: "CSV",
  docx: "DOCX",
  pdf: "PDF",
  xml: "XML",
  image: "IMG",
};

export function QuestionnairesView() {
  const me = useMe();
  const list = useQuestionnaires();
  const upload = useUploadQuestionnaire();
  const canEdit = hasRole(me.data?.role, "editor");
  const items = list.data ?? [];

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title="Questionnaires"
        description="Import a questionnaire in any format. QAutos finds every question and remembers where its answer goes, so the completed file can be exported in the same layout."
      />
      {canEdit && (
        <Uploader
          accept={QUESTIONNAIRE_EXTENSIONS}
          hint={`XLSX · CSV · DOCX · PDF · XML · scans and photos (PNG, JPEG) — up to ${formatBytes(MAX_UPLOAD_BYTES)}`}
          precheck={precheckQuestionnaire}
          upload={(file) => upload.mutateAsync(file)}
          duplicateLabel="Already imported"
        />
      )}
      {list.error ? (
        <ErrorState error={list.error} />
      ) : (
        <Panel
          title="Imported"
          meta={items.some(isQuestionnairePending) ? "Reading… updates automatically" : undefined}
        >
          <Table items={list.data} loading={list.isPending} canEdit={canEdit} />
        </Panel>
      )}
    </div>
  );
}

function Table({
  items,
  loading,
  canEdit,
}: {
  items?: Questionnaire[];
  loading: boolean;
  canEdit: boolean;
}) {
  if (loading) return <Skeleton className="m-5 h-40" />;
  if (!items?.length) {
    return (
      <p className="px-5 py-10 text-center text-sm text-muted-foreground">
        No questionnaires yet.{canEdit ? " Drop one above to get started." : ""}
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-subtle-foreground">
            <th className="px-5 py-2.5 font-medium">Questionnaire</th>
            <th className="px-5 py-2.5 font-medium">Status</th>
            <th className="px-5 py-2.5 text-right font-medium">Questions</th>
            <th className="hidden px-5 py-2.5 font-medium md:table-cell">Imported</th>
            <th className="px-5 py-2.5">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((q) => (
            <Row key={q.id} questionnaire={q} canEdit={canEdit} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({ questionnaire: q, canEdit }: { questionnaire: Questionnaire; canEdit: boolean }) {
  const remove = useDeleteQuestionnaire();
  const status = QUESTIONNAIRE_STATUS[q.status];
  return (
    <tr className="border-b border-border align-top last:border-b-0 hover:bg-muted/30">
      <td className="max-w-0 px-5 py-3 sm:w-[45%]">
        <div className="flex items-center gap-3">
          <span className="flex h-8 w-11 shrink-0 items-center justify-center border border-border bg-surface-raised font-mono text-[10px] text-primary">
            {KIND_LABEL[q.kind] ?? q.kind}
          </span>
          <Link
            href={`/questionnaires/${q.id}`}
            className="min-w-0 truncate font-medium underline-offset-4 hover:text-primary hover:underline"
          >
            {q.filename}
          </Link>
        </div>
      </td>
      <td className="px-5 py-3">
        <Badge tone={status.tone}>
          {isQuestionnairePending(q) && <Spinner />}
          {status.label}
        </Badge>
        {q.status === "failed" && (
          <p className="mt-1 max-w-60 text-xs text-muted-foreground">
            {questionnaireError(q.error_code)}
          </p>
        )}
      </td>
      <td className="px-5 py-3 text-right tabular-nums text-muted-foreground">
        {q.status === "ready" ? q.question_count : "—"}
      </td>
      <td className="hidden px-5 py-3 text-muted-foreground md:table-cell">
        {formatRelative(q.created_at)} · {formatBytes(q.size_bytes)}
      </td>
      <td className="px-5 py-2.5 text-right">
        {canEdit && (
          <Button
            variant="ghost"
            size="sm"
            className="hover:text-manual"
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(`Delete "${q.filename}" and its extracted questions?`)) {
                remove.mutate(q.id);
              }
            }}
          >
            Delete
          </Button>
        )}
      </td>
    </tr>
  );
}
