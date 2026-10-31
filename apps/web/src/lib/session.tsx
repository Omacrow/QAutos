"use client";

import { useAuth } from "@clerk/nextjs";
import { createContext, type ReactNode, use, useMemo, useRef } from "react";

import type { TokenGetter } from "@/lib/api/client";

/**
 * What the app needs from "who is signed in", independent of how: Clerk for
 * real users, or a demo session. Data hooks only ever use this.
 */
export type Session = {
  isLoaded: boolean;
  /** Changes when the active organization changes; used in query keys. */
  orgKey: string | null;
  isDemo: boolean;
  getToken: TokenGetter;
};

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = use(SessionContext);
  if (!session) throw new Error("useSession must be used inside a session provider");
  return session;
}

export function ClerkSessionProvider({ children }: { children: ReactNode }) {
  const { isLoaded, orgId, getToken } = useAuth();
  const value = useMemo<Session>(
    () => ({ isLoaded, orgKey: orgId ?? null, isDemo: false, getToken: () => getToken() }),
    [isLoaded, orgId, getToken],
  );
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function DemoSessionProvider({ children }: { children: ReactNode }) {
  const cached = useRef<{ token: string; expiresAt: number } | null>(null);
  const value = useMemo<Session>(
    () => ({
      isLoaded: true,
      orgKey: "demo",
      isDemo: true,
      getToken: async () => {
        const now = Date.now();
        if (cached.current && cached.current.expiresAt - 30_000 > now) return cached.current.token;
        const response = await fetch("/demo/token", { cache: "no-store" });
        if (!response.ok) return null;
        const { token, expires_in } = (await response.json()) as {
          token: string;
          expires_in: number;
        };
        cached.current = { token, expiresAt: now + expires_in * 1000 };
        return token;
      },
    }),
    [],
  );
  return <SessionContext value={value}>{children}</SessionContext>;
}
