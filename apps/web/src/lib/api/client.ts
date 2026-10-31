import type { components } from "./schema";

export type Me = components["schemas"]["MeOut"];
export type Member = components["schemas"]["MemberOut"];
export type AuditEvent = components["schemas"]["AuditEventOut"];
export type Role = components["schemas"]["Role"];
export type DocumentInfo = components["schemas"]["DocumentOut"];
export type DocumentStatus = components["schemas"]["DocumentStatus"];
export type Chunk = components["schemas"]["ChunkOut"];
export type ChunkPage = components["schemas"]["ChunkPage"];
export type UploadResult = components["schemas"]["UploadOut"];
export type DownloadLink = components["schemas"]["DownloadOut"];
export type SearchResponse = components["schemas"]["SearchOut"];
export type SearchHit = components["schemas"]["SearchHitOut"];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type TokenGetter = () => Promise<string | null>;

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * Call the FastAPI backend with the user's Clerk session token. The API reads
 * the active organization from the token itself, never from the request.
 */
export async function apiFetch<T>(
  path: string,
  getToken: TokenGetter,
  init: RequestInit = {},
  fetchImpl: typeof fetch = fetch,
): Promise<T> {
  const token = await getToken();
  if (!token) throw new ApiError(401, "Not signed in");

  const response = await fetchImpl(`${API_URL}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // non-JSON error body
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Multipart upload. The browser sets the multipart Content-Type itself. */
export function uploadDocument(
  file: File,
  getToken: TokenGetter,
  fetchImpl: typeof fetch = fetch,
): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  return apiFetch<UploadResult>("/v1/documents", getToken, { method: "POST", body }, fetchImpl);
}

const ROLE_RANK: Record<Role, number> = { viewer: 0, editor: 1, owner: 2 };

/** UI-only convenience. The API enforces roles on every request. */
export function hasRole(role: Role | undefined, minimum: Role): boolean {
  return role !== undefined && ROLE_RANK[role] >= ROLE_RANK[minimum];
}
