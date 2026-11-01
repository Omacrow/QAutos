"use client";

import Link from "next/link";
import { use, useMemo, useState } from "react";

import { Spinner } from "@/components/app/document-status";
import { ErrorState, formatRelative, PageHeader, Panel } from "@/components/app/panels";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  hasRole,
  type Question,
  type QuestionnaireDetail as Detail,
  type SheetMappingInput,
} from "@/lib/api/client";
import {
  useMe,
  useQuestionnaire,
  useQuestions,
  useReextract,
  useSetMapping,
  useUpdateQuestion,
} from "@/lib/api/hooks";
import { formatBytes } from "@/lib/documents";
import {
  columnName,
  EXTRACTOR_LABEL,
  isQuestionnairePending,
  locatorLabel,
  QUESTIONNAIRE_STATUS,
  questionnaireError,
} from "@/lib/questionnaires";

type Preview = { sheet: string; row_count: number; rows: string[][] };

export function QuestionnaireDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const record = useQuestionnaire(id);
  const me = useMe();
  const canEdit = hasRole(me.data?.role, "editor");
  const [editingColumns, setEditingColumns] = useState(false);

  if (record.error) return <ErrorState error={record.error} />;
  const q = record.data;
  const status = q ? QUESTIONNAIRE_STATUS[q.status] : null;
  const tabular = q && ["xlsx", "csv", "docx"].includes(q.kind);
  const showMapping = q && canEdit && (q.status === "needs_mapping" || editingColumns);

  return (
    <div className="mx-auto max-w-5xl">
      <Link
        href="/questionnaires"
        className="mb-4 inline-flex font-mono text-xs text-subtle-foreground hover:text-foreground"
      >
        ← Questionnaires
      </Link>
      <PageHeader
        title={q ? <span className="break-all">{q.filename}</span> : <Skeleton className="h-9 w-80" />}
        description={
          q &&
          status && (
            <Badge tone={status.tone}>
              {isQuestionnairePending(q) && <Spinner />}
              {status.label}
            </Badge>
          )
        }
        action={
          q &&
          canEdit &&
          tabular &&
          q.status === "ready" &&
          !editingColumns && (
            <Button variant="secondary" size="sm" onClick={() => setEditingColumns(true)}>
              Change columns
            </Button>
          )
        }
      />
      {q && <Facts q={q} />}
      {q?.status === "failed" && (
        <div className="mb-6 border border-dashed border-manual/40 bg-manual-bg p-5 text-sm">
          <p className="font-medium text-manual">Import failed</p>
          <p className="mt-1 text-muted-foreground">{questionnaireError(q.error_code)}</p>
          {canEdit && <RetryButton id={q.id} />}
        </div>
      )}
      {q && isQuestionnairePending(q) && (
        <div className="mb-6 border border-border bg-surface-solid p-5 text-sm text-muted-foreground">
          Reading the file and finding its questions. This page updates automatically.
        </div>
      )}
      {showMapping && (
        <MappingEditor q={q} onDone={() => setEditingColumns(false)} />
      )}
      {q?.status === "ready" && <Questions id={q.id} canEdit={canEdit} />}
    </div>
  );
}

function Facts({ q }: { q: Detail }) {
  const facts: [string, string][] = [
    ["Format", q.kind === "image" ? "Image" : q.kind.toUpperCase()],
    ["Size", formatBytes(q.size_bytes)],
    ["Questions", q.status === "ready" ? String(q.question_count) : "—"],
    ["Read with", q.extractor ? (EXTRACTOR_LABEL[q.extractor] ?? q.extractor) : "—"],
    ["Columns", q.mapping?.source === "user" ? "Chosen by you" : q.mapping ? "Detected" : "—"],
    ["Imported", `${formatRelative(q.created_at)} by ${q.uploaded_by ?? "system"}`],
  ];
  return (
    <dl className="mb-6 grid grid-cols-2 gap-px border border-border bg-border md:grid-cols-3">
      {facts.map(([label, value]) => (
        <div key={label} className="bg-surface-solid px-5 py-3.5">
          <dt className="font-mono text-[10px] tracking-widest text-subtle-foreground uppercase">
            {label}
          </dt>
          <dd className="mt-1 truncate text-sm">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function RetryButton({ id }: { id: string }) {
  const retry = useReextract(id);
  return (
    <Button
      variant="secondary"
      size="sm"
      className="mt-3"
      disabled={retry.isPending}
      onClick={() => retry.mutate()}
    >
      Try again
    </Button>
  );
}

// --- Column mapping -------------------------------------------------------------------

type Choice = { header_row: number | null; question_col: number | null; answer_col: number | null; ref_col: number | null };

function MappingEditor({ q, onDone }: { q: Detail; onDone: () => void }) {
  const previews = ((q.preview?.sheets ?? []) as Preview[]).filter((p) => p.rows.length);
  const existing = new Map(
    ((q.mapping?.sheets ?? []) as SheetMappingInput[]).map((m) => [m.sheet, m]),
  );
  const [choices, setChoices] = useState<Record<string, Choice>>(() =>
    Object.fromEntries(
      previews.map((p) => {
        const m = existing.get(p.sheet);
        return [
          p.sheet,
          {
            header_row: m ? (m.header_row ?? null) : null,
            question_col: m?.question_col ?? null,
            answer_col: m?.answer_col ?? null,
            ref_col: m?.ref_col ?? null,
          },
        ];
      }),
    ),
  );
  const save = useSetMapping(q.id);
  const chosen = Object.entries(choices).filter(([, c]) => c.question_col !== null);

  function set(sheet: string, patch: Partial<Choice>) {
    setChoices((all) => ({ ...all, [sheet]: { ...all[sheet]!, ...patch } }));
  }

  return (
    <Panel
      title="Which columns hold the questions?"
      meta="Pick at least the question column on one sheet"
      className="mb-6"
    >
      <p className="border-b border-border px-5 py-3 text-xs text-muted-foreground">
        We couldn’t find a header row naming the question column. Choose it below; the answer
        column is where answers will be written on export (leave empty to add a new column).
      </p>
      {previews.map((preview) => {
        const choice = choices[preview.sheet]!;
        const width = Math.max(...preview.rows.map((r) => r.length), 1);
        const columns = Array.from({ length: width }, (_, i) => i);
        return (
          <div key={preview.sheet} className="border-b border-border px-5 py-4 last:border-b-0">
            <div className="flex flex-wrap items-center gap-3">
              <p className="font-medium">{preview.sheet}</p>
              <span className="font-mono text-xs text-subtle-foreground">
                {preview.row_count} rows
              </span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-4">
              <ColumnSelect
                label="Question"
                columns={columns}
                value={choice.question_col}
                onChange={(v) => set(preview.sheet, { question_col: v })}
                emptyLabel="Skip this sheet"
              />
              <ColumnSelect
                label="Answer"
                columns={columns}
                value={choice.answer_col}
                onChange={(v) => set(preview.sheet, { answer_col: v })}
                emptyLabel="Add a column"
              />
              <ColumnSelect
                label="Reference (#, ID)"
                columns={columns}
                value={choice.ref_col}
                onChange={(v) => set(preview.sheet, { ref_col: v })}
                emptyLabel="None"
              />
              <label className="text-xs text-muted-foreground">
                Header row
                <select
                  className="mt-1 block h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
                  value={choice.header_row ?? ""}
                  onChange={(e) =>
                    set(preview.sheet, {
                      header_row: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                >
                  <option value="">No header row</option>
                  {preview.rows.map((_, i) => (
                    <option key={i} value={i}>
                      Row {i + 1}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-3 overflow-x-auto border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-muted/50 text-left font-mono text-subtle-foreground">
                    <th className="w-10 px-2 py-1.5" />
                    {columns.map((c) => (
                      <th
                        key={c}
                        className={`px-2 py-1.5 font-medium ${c === choice.question_col ? "text-primary" : ""}`}
                      >
                        {columnName(c)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((row, r) => (
                    <tr
                      key={r}
                      className={`border-t border-border ${r === choice.header_row ? "bg-muted font-semibold" : ""}`}
                    >
                      <td className="px-2 py-1.5 font-mono text-subtle-foreground">{r + 1}</td>
                      {columns.map((c) => (
                        <td
                          key={c}
                          className={`max-w-64 truncate px-2 py-1.5 ${c === choice.question_col ? "bg-primary/10 text-foreground" : "text-muted-foreground"}`}
                        >
                          {row[c] ?? ""}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
      <div className="flex items-center justify-end gap-2 px-5 py-3">
        {save.error && <p className="mr-auto text-xs text-manual">{save.error.message}</p>}
        {q.status !== "needs_mapping" && (
          <Button variant="ghost" size="sm" onClick={onDone}>
            Cancel
          </Button>
        )}
        <Button
          size="sm"
          disabled={!chosen.length || save.isPending}
          onClick={() =>
            save.mutate(
              chosen.map(([sheet, c]) => ({
                sheet,
                header_row: c.header_row,
                question_col: c.question_col!,
                answer_col: c.answer_col,
                ref_col: c.ref_col,
              })),
              { onSuccess: onDone },
            )
          }
        >
          Extract questions
        </Button>
      </div>
    </Panel>
  );
}

function ColumnSelect({
  label,
  columns,
  value,
  onChange,
  emptyLabel,
}: {
  label: string;
  columns: number[];
  value: number | null;
  onChange: (value: number | null) => void;
  emptyLabel: string;
}) {
  return (
    <label className="text-xs text-muted-foreground">
      {label}
      <select
        className="mt-1 block h-9 w-full rounded-md border border-border bg-background px-2 text-sm text-foreground"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      >
        <option value="">{emptyLabel}</option>
        {columns.map((c) => (
          <option key={c} value={c}>
            Column {columnName(c)}
          </option>
        ))}
      </select>
    </label>
  );
}

// --- Questions --------------------------------------------------------------------------

function Questions({ id, canEdit }: { id: string; canEdit: boolean }) {
  const page = useQuestions(id, true);
  const [showExcluded, setShowExcluded] = useState(true);
  const groups = useMemo(() => {
    const out: { section: string | null; items: Question[] }[] = [];
    for (const question of page.data?.items ?? []) {
      if (!showExcluded && question.excluded) continue;
      const last = out.at(-1);
      if (last && last.section === question.section) last.items.push(question);
      else out.push({ section: question.section, items: [question] });
    }
    return out;
  }, [page.data, showExcluded]);

  if (page.error) return <ErrorState error={page.error} />;
  const items = page.data?.items ?? [];
  const excluded = items.filter((q) => q.excluded).length;
  return (
    <Panel
      title="Extracted questions"
      meta={
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={showExcluded}
            onChange={(e) => setShowExcluded(e.target.checked)}
            className="accent-[var(--primary)]"
          />
          Show excluded ({excluded})
        </label>
      }
    >
      <p className="border-b border-border px-5 py-3 text-xs text-muted-foreground">
        Check the list before answering. Fix a question’s wording, or exclude anything that isn’t a
        question (instructions, headings). Answers are drafted in the next phase.
      </p>
      {page.isPending ? (
        <Skeleton className="m-5 h-48" />
      ) : (
        groups.map((group, g) => (
          <section key={`${group.section}-${g}`}>
            {group.section && (
              <h3 className="border-b border-border bg-muted/40 px-5 py-2 font-mono text-[11px] tracking-wider text-subtle-foreground uppercase">
                {group.section}
              </h3>
            )}
            <ol>
              {group.items.map((question) => (
                <QuestionRow key={question.id} questionnaireId={id} question={question} canEdit={canEdit} />
              ))}
            </ol>
          </section>
        ))
      )}
      {page.data && page.data.total > items.length && (
        <p className="px-5 py-3 text-xs text-muted-foreground">
          Showing the first {items.length} of {page.data.total} questions.
        </p>
      )}
    </Panel>
  );
}

function QuestionRow({
  questionnaireId,
  question,
  canEdit,
}: {
  questionnaireId: string;
  question: Question;
  canEdit: boolean;
}) {
  const update = useUpdateQuestion(questionnaireId);
  const [draft, setDraft] = useState<string | null>(null);
  const location = locatorLabel(question.locator);

  return (
    <li
      className={`grid gap-2 border-b border-border px-5 py-3.5 last:border-b-0 sm:grid-cols-[5.5rem_1fr_auto] ${question.excluded ? "opacity-50" : ""}`}
    >
      <span className="truncate font-mono text-xs text-primary" title={question.ref ?? undefined}>
        {question.ref ?? `#${question.ordinal + 1}`}
      </span>
      <div className="min-w-0">
        {draft !== null ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim().length >= 3) {
                update.mutate({ id: question.id, patch: { text: draft.trim() } });
                setDraft(null);
              }
            }}
          >
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={2}
              autoFocus
              className="w-full rounded-md border border-border bg-background p-2 text-sm focus:border-primary focus:outline-none"
            />
            <div className="mt-1 flex gap-2">
              <Button size="sm" type="submit" disabled={draft.trim().length < 3}>
                Save
              </Button>
              <Button size="sm" variant="ghost" type="button" onClick={() => setDraft(null)}>
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <p className={`text-sm ${question.excluded ? "line-through" : ""}`}>{question.text}</p>
        )}
        <p className="mt-1 flex flex-wrap gap-2 font-mono text-[11px] text-subtle-foreground">
          {location && <span>{location}</span>}
          {question.edited && <span className="text-review">edited</span>}
          {question.excluded && <span>excluded</span>}
        </p>
        {update.error && <p className="mt-1 text-xs text-manual">{update.error.message}</p>}
      </div>
      {canEdit && draft === null && (
        <div className="flex gap-1 sm:justify-end">
          {!question.excluded && (
            <Button variant="ghost" size="sm" onClick={() => setDraft(question.text)}>
              Edit
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => update.mutate({ id: question.id, patch: { excluded: !question.excluded } })}
          >
            {question.excluded ? "Include" : "Exclude"}
          </Button>
        </div>
      )}
    </li>
  );
}
