import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/** Small "+" marks where section rules meet the page's vertical lines. */
function Corners() {
  const mark = "pointer-events-none absolute -top-[5px] size-[9px] text-border-strong";
  return (
    <>
      <svg className={cn(mark, "-left-[5px]")} viewBox="0 0 9 9" aria-hidden>
        <path d="M4.5 0v9M0 4.5h9" stroke="currentColor" />
      </svg>
      <svg className={cn(mark, "-right-[5px]")} viewBox="0 0 9 9" aria-hidden>
        <path d="M4.5 0v9M0 4.5h9" stroke="currentColor" />
      </svg>
    </>
  );
}

/** The page column: vertical lines on both sides, like a ruled sheet. */
export function Frame({ children }: { children: ReactNode }) {
  return <div className="mx-auto max-w-7xl border-x border-border">{children}</div>;
}

export function Section({
  id,
  children,
  className,
  bleed = false,
}: {
  id?: string;
  children: ReactNode;
  className?: string;
  /** Skip inner padding, for edge-to-edge grids. */
  bleed?: boolean;
}) {
  return (
    <section id={id} className={cn("relative scroll-mt-16 border-t border-border", className)}>
      <Corners />
      {bleed ? children : <div className="px-6 py-20 sm:px-10 lg:py-24">{children}</div>}
    </section>
  );
}

export function SectionHeading({
  index,
  eyebrow,
  title,
  description,
  center = false,
}: {
  index?: string;
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  center?: boolean;
}) {
  return (
    <div className={cn("max-w-2xl", center && "mx-auto text-center")}>
      <p className="font-mono text-xs tracking-widest text-primary uppercase">
        {index && <span className="text-subtle-foreground">{index} / </span>}
        {eyebrow}
      </p>
      <h2 className="mt-4 text-3xl font-semibold tracking-tight text-balance sm:text-5xl">{title}</h2>
      {description && (
        <p className="mt-4 text-lg text-pretty text-muted-foreground">{description}</p>
      )}
    </div>
  );
}

/** Edge-to-edge grid whose cells are separated by 1px lines. */
export function GridCells({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("grid gap-px bg-border", className)}>{children}</div>;
}

export function Cell({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("bg-background p-6 sm:p-8", className)}>{children}</div>;
}
