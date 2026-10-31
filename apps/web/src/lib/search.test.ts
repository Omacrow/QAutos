import { describe, expect, it } from "vitest";

import { highlight, queryTerms, viewablePage } from "./search";

describe("queryTerms", () => {
  it("drops stop words, short words and duplicates", () => {
    expect(queryTerms("Is MFA required? Is MFA enforced for the staff?")).toEqual([
      "mfa",
      "required",
      "enforced",
      "staff",
    ]);
  });
  it("keeps version numbers and hyphenated terms whole", () => {
    expect(queryTerms("TLS 1.2 or AES-256")).toEqual(["tls", "1.2", "aes-256"]);
  });
});

describe("highlight", () => {
  it("marks prefix matches case-insensitively", () => {
    const parts = highlight("Data is Encrypted at rest.", ["encrypt"]);
    expect(parts).toEqual([
      { text: "Data is ", match: false },
      { text: "Encrypt", match: true },
      { text: "ed at rest.", match: false },
    ]);
  });
  it("does not match inside words", () => {
    expect(highlight("unencrypted", ["encrypt"])).toEqual([{ text: "unencrypted", match: false }]);
  });
  it("treats regex characters literally", () => {
    expect(highlight("Uses TLS 1.2 and 152", ["1.2"]).filter((s) => s.match)).toEqual([
      { text: "1.2", match: true },
    ]);
  });
  it("returns the text untouched with no terms", () => {
    expect(highlight("abc", [])).toEqual([{ text: "abc", match: false }]);
  });
});

describe("viewablePage", () => {
  it("opens PDFs directly and DOCX through the rendition", () => {
    expect(viewablePage({ document_kind: "pdf", document_has_rendition: false, page_start: 4 })).toEqual({ rendition: false, page: 4 });
    expect(viewablePage({ document_kind: "docx", document_has_rendition: true, page_start: 2 })).toEqual({ rendition: true, page: 2 });
    expect(viewablePage({ document_kind: "docx", document_has_rendition: false, page_start: 1 })).toBeNull();
    expect(viewablePage({ document_kind: "xlsx", document_has_rendition: false, page_start: null })).toBeNull();
  });
});
