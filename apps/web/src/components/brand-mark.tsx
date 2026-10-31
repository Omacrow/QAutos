import { BRAND } from "@/config/brand";

export function BrandMark() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold tracking-tight text-foreground">
      <svg viewBox="0 0 24 24" className="size-6" aria-hidden>
        <path d="M4 15 L12 4 L20 15 Z" fill="var(--primary)" />
        <path d="M8 20 L16 9 L20 15 L12 20 Z" fill="var(--accent)" opacity="0.9" />
      </svg>
      {BRAND.name}
    </span>
  );
}
