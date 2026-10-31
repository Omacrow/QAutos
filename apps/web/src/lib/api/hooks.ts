"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { isPending } from "@/lib/documents";
import { useSession } from "@/lib/session";

import {
  type AuditEvent,
  apiFetch,
  type ChunkPage,
  type DocumentInfo,
  type DownloadLink,
  type Me,
  type Member,
  uploadDocument,
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

/** Refresh document lists, detail views and the audit log after a change. */
function useInvalidateDocuments() {
  const queryClient = useQueryClient();
  const { orgKey } = useSession();
  return () =>
    queryClient.invalidateQueries({
      predicate: ({ queryKey }) =>
        queryKey[0] === orgKey &&
        typeof queryKey[1] === "string" &&
        (queryKey[1].startsWith("/v1/documents") || queryKey[1].startsWith("/v1/audit-events")),
    });
}

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
