/**
 * Demo mode: a "Try the demo" login into a shared, pre-seeded demo
 * organization, without a Clerk account. The API independently requires
 * DEMO_JWT_SECRET and pins every demo session to the demo org only.
 */
export const DEMO_ENABLED = process.env.NEXT_PUBLIC_DEMO_MODE === "1";

export const DEMO_COOKIE = "sqa_demo";
