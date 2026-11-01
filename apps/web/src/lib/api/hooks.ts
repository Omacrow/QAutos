"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { isPending } from "@/lib/documents";
import { isQuestionnairePending } from "@/lib/questionnaires";
import { useSession } from "@/lib/session";

import {
  type AuditEvent,
  apiFetch,
  type ChunkPage,
  type DocumentInfo,
  type DownloadLink,
  type Me,
  type Member,
  type Question,
  type Questionnaire,
  type QuestionnaireDetail,
  type QuestionPage,
  type SearchResponse,
  type SheetMappingInput,
  uploadDocument,
  uploadQuestionnaire,
} from "./client";

const POLL_MS = 2000;

/** Query keys include the org so switching orgs never shows stale data. */
function useOrgQuery<T>(
  path: string,
  { enabled = true, poll }: { enabled?: boolean; poll?: (data: T | undefined) => boolean } = {},
) {
  const { getToken, orgKey, isLoaded } = useSession();
  return useQuery({
    queryKey: [orgKey, path],
    queryFn: () => apiFetch<T>(path, getToken),
    enabled: isLoaded && Boolean(orgKey) && enabled,
    refetchInterval: poll ? (query) => (poll(query.state.data) ? POLL_MS : false) : undefined,
  });
}

export const useMe = () => useOrgQuery<Me>("/v1/me");
export const useMembers = () => useOrgQuery<Member[]>("/v1/org/members");
export const useAuditEvents = (enabled: boolean, limit = 20) =>
  useOrgQuery<AuditEvent[]>(`/v1/audit-events?limit=${limit}`, { enabled });

// --- Documents -----------------------------------------------------------------

/** Polls while any document is still being processed. */
export const useDocuments = () =>
  useOrgQuery<DocumentInfo[]>("/v1/documents", { poll: (docs) => Boolean(docs?.some(isPending)) });

export const useDocument = (id: string) =>
  useOrgQuery<DocumentInfo>(`/v1/documents/${id}`, {
    poll: (doc) => doc !== undefined && isPending(doc),
  });

export const useChunks = (id: string, offset: number, limit: number, enabled: boolean) =>
  useOrgQuery<ChunkPage>(`/v1/documents/${id}/chunks?offset=${offset}&limit=${limit}`, {
    enabled,
  });

/** Refresh every cached query under these path prefixes (plus the audit log). */
function useInvalidate(prefix: string) {
  const queryClient = useQueryClient();
  const { orgKey } = useSession();
  return () =>
    queryClient.invalidateQueries({
      predicate: ({ queryKey }) =>
        queryKey[0] === orgKey &&
        typeof queryKey[1] === "string" &&
        (queryKey[1].startsWith(prefix) || queryKey[1].startsWith("/v1/audit-events")),
    });
}

const useInvalidateDocuments = () => useInvalidate("/v1/documents");

export function useUploadDocument() {
  const { getToken } = useSession();
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (file: File) => uploadDocument(file, getToken),
    onSettled: invalidate,
  });
}

export function useDeleteDocument() {
  const { getToken } = useSession();
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/v1/documents/${id}`, getToken, { method: "DELETE" }),
    onSettled: invalidate,
  });
}

export function useReprocessDocument() {
  const { getToken } = useSession();
  const invalidate = useInvalidateDocuments();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<DocumentInfo>(`/v1/documents/${id}/reprocess`, getToken, { method: "POST" }),
    onSettled: invalidate,
  });
}

/** Search is a POST (the question stays out of URLs and logs); cached per question. */
export function useSearch(query: string, documentIds?: string[]) {
  const { getToken, orgKey, isLoaded } = useSession();
  return useQuery({
    queryKey: [orgKey, "/v1/search", query, documentIds ?? null],
    queryFn: () =>
      apiFetch<SearchResponse>("/v1/search", getToken, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, limit: 10, document_ids: documentIds ?? null }),
      }),
    enabled: isLoaded && Boolean(orgKey) && query.trim().length >= 2,
    staleTime: 60_000,
  });
}

/**
 * Open a PDF (or a DOCX's PDF rendition) in a new tab at a page. The tab opens
 * synchronously on click, so popup blockers allow it, then gets the signed link.
 */
export function useOpenAtPage() {
  const { getToken } = useSession();
  return useMutation({
    mutationFn: async ({
      id,
      page,
      rendition,
    }: {
      id: string;
      page: number | null;
      rendition: boolean;
    }) => {
      const tab = window.open("", "_blank");
      try {
        const params = new URLSearchParams({ inline: "true" });
        if (rendition) params.set("rendition", "true");
        const { url } = await apiFetch<DownloadLink>(
          `/v1/documents/${id}/download?${params}`,
          getToken,
          { method: "POST" },
        );
        if (tab) {
          tab.opener = null;
          tab.location.href = page ? `${url}#page=${page}` : url;
        }
      } catch (error) {
        tab?.close();
        throw error;
      }
    },
  });
}

/** Fetch a short-lived signed link and hand it to the browser, which downloads it. */
export function useDownloadDocument() {
  const { getToken } = useSession();
  return useMutation({
    mutationFn: ({ id, rendition = false }: { id: string; rendition?: boolean }) =>
      apiFetch<DownloadLink>(
        `/v1/documents/${id}/download${rendition ? "?rendition=true" : ""}`,
        getToken,
        { method: "POST" },
      ),
    onSuccess: ({ url }) => window.location.assign(url),
  });
}

// --- Questionnaires ------------------------------------------------------------------

export const useQuestionnaires = () =>
  useOrgQuery<Questionnaire[]>("/v1/questionnaires", {
    poll: (items) => Boolean(items?.some(isQuestionnairePending)),
  });

export const useQuestionnaire = (id: string) =>
  useOrgQuery<QuestionnaireDetail>(`/v1/questionnaires/${id}`, {
    poll: (q) => q !== undefined && isQuestionnairePending(q),
  });

/** All questions (up to 500, the API page limit; questionnaires rarely exceed it). */
export const useQuestions = (id: string, enabled: boolean) =>
  useOrgQuery<QuestionPage>(`/v1/questionnaires/${id}/questions?limit=500`, { enabled });

export function useUploadQuestionnaire() {
  const { getToken } = useSession();
  const invalidate = useInvalidate("/v1/questionnaires");
  return useMutation({
    mutationFn: (file: File) => uploadQuestionnaire(file, getToken),
    onSettled: invalidate,
  });
}

export function useSetMapping(id: string) {
  const { getToken } = useSession();
  const invalidate = useInvalidate("/v1/questionnaires");
  return useMutation({
    mutationFn: (sheets: SheetMappingInput[]) =>
      apiFetch<QuestionnaireDetail>(`/v1/questionnaires/${id}/mapping`, getToken, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sheets }),
      }),
    onSettled: invalidate,
  });
}

export function useReextract(id: string) {
  const { getToken } = useSession();
  const invalidate = useInvalidate("/v1/questionnaires");
  return useMutation({
    mutationFn: () =>
      apiFetch<QuestionnaireDetail>(`/v1/questionnaires/${id}/reextract`, getToken, {
        method: "POST",
      }),
    onSettled: invalidate,
  });
}

/** Edit or exclude one question. The list updates immediately and rolls back on error. */
export function useUpdateQuestion(questionnaireId: string) {
  const { getToken, orgKey } = useSession();
  const queryClient = useQueryClient();
  const key = [orgKey, `/v1/questionnaires/${questionnaireId}/questions?limit=500`];
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { text?: string; excluded?: boolean } }) =>
      apiFetch<Question>(`/v1/questionnaires/${questionnaireId}/questions/${id}`, getToken, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      }),
    onMutate: async ({ id, patch }) => {
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<QuestionPage>(key);
      queryClient.setQueryData<QuestionPage>(key, (page) =>
        page && {
          ...page,
          items: page.items.map((q) =>
            q.id === id ? { ...q, ...patch, edited: q.edited || patch.text !== undefined } : q,
          ),
        },
      );
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(key, context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: key }),
  });
}

export function useDeleteQuestionnaire() {
  const { getToken } = useSession();
  const invalidate = useInvalidate("/v1/questionnaires");
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/v1/questionnaires/${id}`, getToken, { method: "DELETE" }),
    onSettled: invalidate,
  });
}
