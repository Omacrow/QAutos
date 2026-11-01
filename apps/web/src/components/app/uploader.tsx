"use client";

import { type DragEvent, useId, useState } from "react";

import { Spinner } from "@/components/app/document-status";
import { Badge } from "@/components/ui/badge";
import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/cn";

/** Drag-and-drop multi-file upload with per-file progress. Files upload one at a time. */
type UploadItem = {
  key: string;
  name: string;
  state: "waiting" | "uploading" | "done" | "duplicate" | "error";
  message?: string;
};

export function Uploader({
  accept,
  hint,
  precheck,
  upload,
  duplicateLabel = "Already uploaded",
}: {
  accept: readonly string[];
  hint: string;
  precheck: (file: File) => string | null;
  upload: (file: File) => Promise<{ duplicate: boolean }>;
  duplicateLabel?: string;
}) {
  const inputId = useId();
  const [items, setItems] = useState<UploadItem[]>([]);
  const [dragging, setDragging] = useState(false);

  const update = (key: string, patch: Partial<UploadItem>) =>
    setItems((current) => current.map((i) => (i.key === key ? { ...i, ...patch } : i)));

  async function handleFiles(files: FileList | File[]) {
    const batch = Array.from(files).map((file) => {
      const problem = precheck(file);
      const item: UploadItem = {
        key: `${file.name}-${file.size}-${crypto.randomUUID()}`,
        name: file.name,
        state: problem ? "error" : "waiting",
        message: problem ?? undefined,
      };
      return { file, item, problem };
    });
    setItems((current) => [...batch.map((b) => b.item), ...current].slice(0, 20));

    // One at a time: keeps the API and the background workers within rate limits.
    for (const { file, item, problem } of batch) {
      if (problem) continue;
      update(item.key, { state: "uploading" });
      try {
        const result = await upload(file);
        update(item.key, result.duplicate ? { state: "duplicate" } : { state: "done" });
      } catch (error) {
        update(item.key, {
          state: "error",
          message: error instanceof ApiError ? error.message : "Upload failed.",
        });
      }
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length) void handleFiles(event.dataTransfer.files);
  }

  return (
    <div className="mb-6 border border-border bg-surface-solid">
      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "grid-backdrop flex cursor-pointer flex-col items-center gap-3 px-6 py-10 text-center transition-colors",
          dragging
            ? "bg-primary/10 outline-2 -outline-offset-8 outline-primary outline-dashed"
            : "hover:bg-muted/40",
        )}
      >
        <span className="flex size-11 items-center justify-center border border-border bg-surface-raised text-primary">
          <svg viewBox="0 0 24 24" className="size-5" aria-hidden>
            <path
              d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <span>
          <span className="font-medium">Drop files here</span>{" "}
          <span className="text-muted-foreground">or</span>{" "}
          <span className="font-medium text-primary underline-offset-4 hover:underline">browse</span>
        </span>
        <span className="font-mono text-xs text-subtle-foreground">
          {hint}
        </span>
        <input
          id={inputId}
          type="file"
          multiple
          accept={accept.join(",")}
          className="sr-only"
          onChange={(e) => {
            if (e.target.files?.length) void handleFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
      {items.length > 0 && (
        <ul className="border-t border-border">
          {items.map((item) => (
            <li
              key={item.key}
              className="flex items-center justify-between gap-4 border-b border-border px-5 py-2.5 text-sm last:border-b-0"
            >
              <span className="min-w-0 truncate">{item.name}</span>
              <UploadState item={item} duplicateLabel={duplicateLabel} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UploadState({ item, duplicateLabel }: { item: UploadItem; duplicateLabel: string }) {
  switch (item.state) {
    case "waiting":
      return <Badge>Waiting</Badge>;
    case "uploading":
      return (
        <Badge tone="review">
          <Spinner /> Uploading
        </Badge>
      );
    case "done":
      return <Badge tone="approved">Uploaded</Badge>;
    case "duplicate":
      return <Badge tone="library">{duplicateLabel}</Badge>;
    case "error":
      return (
        <span className="text-right text-xs text-manual">{item.message ?? "Upload failed."}</span>
      );
  }
}
