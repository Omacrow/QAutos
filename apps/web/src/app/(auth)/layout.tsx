import type { ReactNode } from "react";

import { ClerkRoot } from "@/components/clerk-root";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return <ClerkRoot>{children}</ClerkRoot>;
}
