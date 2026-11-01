"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

type NavItem = { href: string; label: string; phase?: string };

const SECTIONS: { title: string; items: NavItem[] }[] = [
  {
    title: "Workspace",
    items: [
      { href: "/dashboard", label: "Overview" },
      { href: "/documents", label: "Documents" },
      { href: "/search", label: "Search" },
      { href: "/questionnaires", label: "Questionnaires" },
      { href: "/library", label: "Answer Library", phase: "4" },
    ],
  },
  {
    title: "Admin",
    items: [
      { href: "/members", label: "Members" },
      { href: "/audit", label: "Audit log" },
      { href: "/settings", label: "Settings" },
    ],
  },
];

export function SideNav() {
  const pathname = usePathname();
  return (
    <nav className="flex flex-col gap-6 p-3 pt-6" aria-label="Main">
      {SECTIONS.map((section) => (
        <div key={section.title}>
          <p className="px-3 pb-2 font-mono text-[10px] tracking-widest text-subtle-foreground uppercase">
            {section.title}
          </p>
          <ul className="flex flex-col gap-0.5">
            {section.items.map((item) => (
              <li key={item.href}>
                <NavLink item={item} active={pathname.startsWith(item.href)} />
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  if (item.phase) {
    return (
      <span
        className="flex items-center justify-between rounded-sm px-3 py-2 text-sm text-subtle-foreground"
        aria-disabled
      >
        {item.label}
        <span className="border border-border px-1.5 font-mono text-[10px] uppercase">soon</span>
      </span>
    );
  }
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "relative flex rounded-sm px-3 py-2 text-sm transition-colors",
        active
          ? "bg-muted text-foreground before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:bg-primary"
          : "text-muted-foreground hover:bg-muted hover:text-foreground",
      )}
    >
      {item.label}
    </Link>
  );
}
