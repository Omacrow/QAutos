import { NextResponse, type NextRequest } from "next/server";

import { DEMO_COOKIE, DEMO_ENABLED } from "@/config/demo";

/** "Try the demo": mark this browser as a demo session and open the app. */
export function GET(request: NextRequest) {
  if (!DEMO_ENABLED) return new NextResponse(null, { status: 404 });
  // Relative Location: correct behind proxies, unlike the server's bind address.
  const response = new NextResponse(null, { status: 307, headers: { Location: "/dashboard" } });
  response.cookies.set(DEMO_COOKIE, "1", {
    httpOnly: true,
    sameSite: "lax",
    secure: request.headers.get("x-forwarded-proto") === "https",
    path: "/",
    maxAge: 60 * 60 * 8,
  });
  return response;
}
