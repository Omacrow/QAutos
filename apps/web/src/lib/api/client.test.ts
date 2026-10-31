import { describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch, hasRole, uploadDocument } from "./client";

const token = () => Promise.resolve("tok_123");

function fakeFetch(status: number, body: unknown) {
  return vi.fn(
    async () =>
      new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
}

describe("apiFetch", () => {
  it("sends the bearer token and parses JSON", async () => {
    const f = fakeFetch(200, { ok: true });
    await expect(apiFetch("/v1/me", token, {}, f)).resolves.toEqual({ ok: true });
    const init = f.mock.calls[0] as unknown as [string, RequestInit];
    expect((init[1].headers as Record<string, string>).Authorization).toBe("Bearer tok_123");
  });

  it("surfaces the API's error detail", async () => {
    const f = fakeFetch(403, { detail: "Insufficient role" });
    await expect(apiFetch("/v1/audit-events", token, {}, f)).rejects.toMatchObject({
      status: 403,
      message: "Insufficient role",
    });
  });

  it("refuses to call the API without a token", async () => {
    const f = fakeFetch(200, {});
    await expect(apiFetch("/v1/me", () => Promise.resolve(null), {}, f)).rejects.toBeInstanceOf(
      ApiError,
    );
    expect(f).not.toHaveBeenCalled();
  });

  it("handles 204", async () => {
    await expect(apiFetch("/x", token, {}, fakeFetch(204, undefined))).resolves.toBeUndefined();
  });
});

describe("hasRole", () => {
  it("orders roles", () => {
    expect(hasRole("owner", "editor")).toBe(true);
    expect(hasRole("viewer", "editor")).toBe(false);
    expect(hasRole(undefined, "viewer")).toBe(false);
  });
});

describe("uploadDocument", () => {
  it("posts multipart form data and lets the browser set the boundary", async () => {
    const f = fakeFetch(201, { document: { id: "d1" }, duplicate: false });
    const file = new File(["%PDF-1.7"], "Policy.pdf", { type: "application/pdf" });
    await expect(uploadDocument(file, token, f)).resolves.toMatchObject({ duplicate: false });
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/v1\/documents$/);
    expect(init.method).toBe("POST");
    expect((init.body as FormData).get("file")).toBeInstanceOf(File);
    expect(Object.keys(init.headers as Record<string, string>)).toEqual(["Authorization"]);
  });
});
