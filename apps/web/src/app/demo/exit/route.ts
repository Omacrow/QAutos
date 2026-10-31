import { NextResponse } from "next/server";

import { DEMO_COOKIE } from "@/config/demo";

export function GET() {
  const response = new NextResponse(null, { status: 307, headers: { Location: "/" } });
  response.cookies.delete(DEMO_COOKIE);
  return response;
}
