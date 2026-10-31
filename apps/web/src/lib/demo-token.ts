import "server-only";

import { createHmac } from "node:crypto";

export const DEMO_ISSUER = "sqa-demo";
export const DEMO_TOKEN_TTL_SECONDS = 300;

/**
 * Mint a short-lived HS256 demo token. The API pins every demo token to the
 * demo organization, so the claims here can't widen access.
 */
export function mintDemoToken(secret: string, now = Math.floor(Date.now() / 1000)): string {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const header = encode({ alg: "HS256", typ: "JWT" });
  const payload = encode({
    iss: DEMO_ISSUER,
    sub: "visitor",
    iat: now,
    exp: now + DEMO_TOKEN_TTL_SECONDS,
  });
  const signature = createHmac("sha256", secret).update(`${header}.${payload}`).digest("base64url");
  return `${header}.${payload}.${signature}`;
}
