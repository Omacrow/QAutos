import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { cookies } from "next/headers";
import Link from "next/link";
import { type ReactNode, Suspense } from "react";

import { BrandMark } from "@/components/brand-mark";
import { Badge } from "@/components/ui/badge";
import { buttonClasses } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { DEMO_COOKIE, DEMO_ENABLED } from "@/config/demo";
import { ClerkSessionProvider, DemoSessionProvider } from "@/lib/session";
import { SideNav } from "./side-nav";

// The session (demo cookie or Clerk) is read at request time, so the shell
// streams in behind Suspense (required by Cache Components).
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={<ShellSkeleton />}>
      <SessionShell>{children}</SessionShell>
    </Suspense>
  );
}

async function SessionShell({ children }: { children: ReactNode }) {
  const isDemo = DEMO_ENABLED && (await cookies()).get(DEMO_COOKIE)?.value === "1";
  const shell = (
    <Shell header={isDemo ? <DemoHeader /> : <ClerkHeader />} isDemo={isDemo}>
      {children}
    </Shell>
  );
  return isDemo ? (
    <DemoSessionProvider>{shell}</DemoSessionProvider>
  ) : (
    <ClerkSessionProvider>{shell}</ClerkSessionProvider>
  );
}

function Shell({
  header,
  isDemo,
  children,
}: {
  header: ReactNode;
  isDemo: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-border bg-surface-solid md:flex">
        <Link href="/dashboard" className="flex h-16 items-center border-b border-border px-5">
          <BrandMark />
        </Link>
        <SideNav />
        {isDemo && (
          <div className="mt-auto border-t border-border p-5 text-xs text-muted-foreground">
            You&apos;re exploring a shared demo workspace with sample data.
          </div>
        )}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between gap-4 border-b border-border bg-background/80 px-6 backdrop-blur-md">
          {header}
        </header>
        <main className="flex-1 p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

function ClerkHeader() {
  return (
    <>
      <OrganizationSwitcher
        hidePersonal
        afterSelectOrganizationUrl="/dashboard"
        afterCreateOrganizationUrl="/dashboard"
      />
      <UserButton />
    </>
  );
}

function DemoHeader() {
  return (
    <>
      <div className="flex items-center gap-3">
        <Badge tone="primary">Demo</Badge>
        <span className="text-sm text-muted-foreground">Northwind (Demo) · Owner</span>
      </div>
      <Link href="/demo/exit" className={buttonClasses("secondary", "sm")} prefetch={false}>
        Exit demo
      </Link>
    </>
  );
}

function ShellSkeleton() {
  return (
    <div className="flex min-h-screen">
      <div className="hidden w-64 border-r border-border bg-surface-solid md:block" />
      <div className="flex-1 p-8">
        <Skeleton className="h-9 w-64" />
        <Skeleton className="mt-6 h-40" />
      </div>
    </div>
  );
}
