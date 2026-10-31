import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { buttonClasses } from "@/components/ui/button";
import { DEMO_ENABLED } from "@/config/demo";
import { REPO_URL, STATIC_PREVIEW } from "@/config/site";
import { NAV_LINKS } from "@/content/marketing";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 border-x border-border px-6 sm:px-10">
        <Link href="/" aria-label="Home">
          <BrandMark />
        </Link>
        <nav className="hidden items-center gap-7 text-sm text-muted-foreground lg:flex" aria-label="Sections">
          {NAV_LINKS.map((l) => (
            <a key={l.href} href={l.href} className="transition-colors hover:text-foreground">
              {l.label}
            </a>
          ))}
        </nav>
        {STATIC_PREVIEW ? (
          <div className="flex items-center gap-2">
            <a href={REPO_URL} className={buttonClasses("ghost", "sm")}>
              GitHub
            </a>
            <a href="#demo" className={buttonClasses("primary", "sm")}>
              See the live demo
            </a>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <Link href="/sign-in" className={buttonClasses("ghost", "sm")}>
              Log in
            </Link>
            <Link
              href={DEMO_ENABLED ? "/demo" : "/sign-up"}
              className={buttonClasses("primary", "sm")}
            >
              {DEMO_ENABLED ? "Try the demo" : "Get started"}
            </Link>
          </div>
        )}
      </div>
    </header>
  );
}
