import { NextResponse, type NextRequest } from "next/server";

import { DEMO_COOKIE, DEMO_ENABLED } from "@/config/demo";
import { DEMO_TOKEN_TTL_SECONDS, mintDemoToken } from "@/lib/demo-token";

/** Short-lived API token for a demo session (the demo's stand-in for Clerk's getToken). */
export function GET(request: NextRequest) {
  const secret = process.env.DEMO_JWT_SECRET;
  if (!DEMO_ENABLED || !secret || request.cookies.get(DEMO_COOKIE)?.value !== "1") {
    return NextResponse.json({ detail: "Not in a demo session" }, { status: 401 });
  }
  return NextResponse.json(
    { token: mintDemoToken(secret), expires_in: DEMO_TOKEN_TTL_SECONDS },
    { headers: { "Cache-Control": "no-store" } },
  );
}
