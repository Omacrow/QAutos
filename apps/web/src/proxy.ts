import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { type NextFetchEvent, type NextRequest, NextResponse } from "next/server";

import { DEMO_COOKIE, DEMO_ENABLED } from "@/config/demo";

// Everything except the landing page and auth screens requires sign-in.
// This is an optimistic check for UX; the API verifies every request itself.
const isPublic = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)"]);
const isDemoRoute = createRouteMatcher(["/demo(.*)"]);

const clerk = clerkMiddleware(async (auth, request) => {
  if (!isPublic(request)) await auth.protect();
});

export default function proxy(request: NextRequest, event: NextFetchEvent) {
  // Demo sessions don't use Clerk; the API pins demo tokens to the demo org.
  if (DEMO_ENABLED && (isDemoRoute(request) || request.cookies.get(DEMO_COOKIE)?.value === "1")) {
    return NextResponse.next();
  }
  return clerk(request, event);
}

export const config = {
  matcher: [
    // `.+` skips the bare landing page "/": it needs no auth, and skipping it
    // avoids a Clerk handshake round-trip for anonymous visitors.
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).+)",
    "/(api|trpc)(.*)",
  ],
};
