import { ClerkProvider } from "@clerk/nextjs";
import type { ReactNode } from "react";

// Clerk's UI reads the same tokens as the rest of the app.
const clerkAppearance = {
  variables: {
    colorPrimary: "var(--primary)",
    colorPrimaryForeground: "var(--primary-foreground)",
    colorBackground: "var(--surface-solid)",
    colorForeground: "var(--foreground)",
    colorMutedForeground: "var(--muted-foreground)",
    colorInput: "var(--surface-raised)",
    colorInputForeground: "var(--foreground)",
    colorBorder: "var(--border-strong)",
    colorDanger: "var(--danger)",
    colorSuccess: "var(--success)",
    colorWarning: "var(--warning)",
    fontFamily: "var(--font-sans-family)",
    borderRadius: "var(--radius)",
  },
};

/**
 * Clerk wraps only the sign-in pages and the workspace. The marketing site
 * doesn't need it, which lets it be exported as static files (GitHub Pages).
 */
export function ClerkRoot({ children }: { children: ReactNode }) {
  return <ClerkProvider appearance={clerkAppearance}>{children}</ClerkProvider>;
}
