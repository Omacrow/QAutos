import { createHmac } from "node:crypto";

import { describe, expect, it } from "vitest";

import { DEMO_ISSUER, DEMO_TOKEN_TTL_SECONDS, mintDemoToken } from "./demo-token";

const SECRET = "s".repeat(40);

describe("mintDemoToken", () => {
  it("produces a valid HS256 JWT with the demo issuer and a short expiry", () => {
    const token = mintDemoToken(SECRET, 1_000);
    const [header, payload, signature] = token.split(".");
    const expected = createHmac("sha256", SECRET).update(`${header}.${payload}`).digest("base64url");
    expect(signature).toBe(expected);

    const claims = JSON.parse(Buffer.from(payload, "base64url").toString());
    expect(claims).toEqual({
      iss: DEMO_ISSUER,
      sub: "visitor",
      iat: 1_000,
      exp: 1_000 + DEMO_TOKEN_TTL_SECONDS,
    });
    expect(JSON.parse(Buffer.from(header, "base64url").toString()).alg).toBe("HS256");
  });

  it("does not carry any org claim (the API pins demo to the demo org)", () => {
    const payload = JSON.parse(Buffer.from(mintDemoToken(SECRET).split(".")[1], "base64url").toString());
    expect(payload).not.toHaveProperty("org_id");
    expect(payload).not.toHaveProperty("o");
  });
});
