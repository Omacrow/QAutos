import Link from "next/link";

import { BrandMark } from "@/components/brand-mark";
import { Cell, Frame, GridCells, Section, SectionHeading } from "@/components/marketing/frame";
import { LiveDemo } from "@/components/marketing/live-demo";
import { SiteHeader } from "@/components/marketing/site-header";
import { buttonClasses } from "@/components/ui/button";
import { BRAND } from "@/config/brand";
import { DEMO_ENABLED } from "@/config/demo";
import { REPO_URL, STATIC_PREVIEW } from "@/config/site";
import {
  COMPARISON,
  CONFIDENCE_SIGNALS,
  FAQ,
  FEATURES,
  FRAMEWORKS,
  LOGOS,
  SECURITY_POINTS,
  STATS,
  STEPS,
  TESTIMONIALS,
} from "@/content/marketing";

const primaryCta = STATIC_PREVIEW
  ? { href: "#demo", label: "See the live demo" }
  : DEMO_ENABLED
    ? { href: "/demo", label: "Try the live demo" }
    : { href: "/sign-up", label: "Get started" };

// Static preview: no accounts yet, so the second action points at the code.
const secondaryCta = STATIC_PREVIEW
  ? { href: REPO_URL, label: "Follow the build on GitHub" }
  : { href: "/sign-up", label: "Create an account" };

export default function Landing() {
  return (
    <>
      <SiteHeader />
      <Frame>
        <Hero />
        <LogoStrip />
        <Stats />
        <Section id="demo">
          <SectionHeading
            index="01"
            eyebrow="Live demo"
            title="Watch a questionnaire answer itself, or refuse to."
            description="Pick a question. You'll see the same steps the product runs: search, rerank, draft, verify. The last one shows what happens when your documents don't have the answer."
          />
          <div className="mt-12 border border-border">
            <LiveDemo />
          </div>
          {DEMO_ENABLED && !STATIC_PREVIEW && (
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <Link href="/demo" className={buttonClasses("primary", "md")}>
                Open the demo workspace →
              </Link>
              <p className="text-sm text-muted-foreground">
                Signs you into a sample organization. No account needed.
              </p>
            </div>
          )}
        </Section>
        <HowItWorks />
        <Features />
        <Confidence />
        <Testimonials />
        <Comparison />
        <Security />
        <Faq />
        <FinalCta />
      </Frame>
      <SiteFooter />
    </>
  );
}

function Hero() {
  return (
    <section className="grid-backdrop relative overflow-hidden px-6 pt-20 pb-24 sm:px-10 lg:pt-28">
      <div className="pointer-events-none absolute -top-40 right-0 size-[520px] rounded-full bg-primary/20 blur-[120px]" />
      <div className="relative">
        <p className="inline-flex items-center gap-2 border border-border bg-background px-3 py-1 font-mono text-xs tracking-widest text-muted-foreground uppercase">
          <span className="size-1.5 rounded-full bg-primary" />
          AI for security questionnaires
        </p>
        <h1 className="mt-8 max-w-5xl text-5xl leading-[0.92] font-semibold tracking-tight uppercase sm:text-7xl lg:text-[104px]">
          Security reviews,
          <br />
          <span className="text-primary">answered</span> with proof.
        </h1>
        <div className="mt-10 grid gap-10 lg:grid-cols-[1fr_auto] lg:items-end">
          <p className="max-w-xl text-lg text-pretty text-muted-foreground">
            Upload your policies and past questionnaires. Every drafted answer cites the exact page it
            came from, carries a confidence score you can audit, and is left blank when the evidence
            isn&apos;t there.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href={primaryCta.href} className={buttonClasses("primary", "lg")}>
              {primaryCta.label.toUpperCase()}
            </Link>
            <a href="#how" className={buttonClasses("secondary", "lg")}>
              How it works
            </a>
          </div>
        </div>
        <ul className="mt-14 flex flex-wrap gap-2">
          {FRAMEWORKS.map((f) => (
            <li
              key={f}
              className="border border-border bg-background px-3 py-1.5 font-mono text-xs text-muted-foreground"
            >
              {f}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function LogoStrip() {
  return (
    <Section bleed>
      <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3 lg:grid-cols-6">
        {LOGOS.map((name, i) => (
          <div
            key={name}
            className="flex h-24 items-center justify-center bg-background text-lg font-semibold tracking-tight text-subtle-foreground"
            style={{ fontStyle: i % 3 === 1 ? "italic" : undefined }}
          >
            {name}
          </div>
        ))}
      </div>
    </Section>
  );
}

function Stats() {
  return (
    <Section bleed>
      <GridCells className="sm:grid-cols-2 lg:grid-cols-4">
        {STATS.map((s) => (
          <Cell key={s.label}>
            <p className="text-5xl font-semibold tracking-tight text-primary tabular-nums">{s.value}</p>
            <p className="mt-3 text-sm text-muted-foreground">{s.label}</p>
          </Cell>
        ))}
      </GridCells>
    </Section>
  );
}

function HowItWorks() {
  return (
    <Section id="how" bleed>
      <div className="px-6 pt-20 pb-12 sm:px-10 lg:pt-24">
        <SectionHeading
          index="02"
          eyebrow="How it works"
          title="From spreadsheet to sent in four steps."
        />
      </div>
      <GridCells className="border-t border-border md:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s, i) => (
          <Cell key={s.title} className="min-h-64">
            <p className="font-mono text-sm text-primary">0{i + 1}</p>
            <h3 className="mt-10 text-xl font-semibold">{s.title}</h3>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">{s.body}</p>
          </Cell>
        ))}
      </GridCells>
    </Section>
  );
}

function Features() {
  return (
    <Section bleed>
      <div className="px-6 pt-20 pb-12 sm:px-10 lg:pt-24">
        <SectionHeading
          index="03"
          eyebrow="Built for accuracy"
          title="Every answer traceable. Every gap visible."
        />
      </div>
      <GridCells className="border-t border-border md:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <Cell key={f.title} className="group transition-colors hover:bg-surface-solid">
            <div className="flex size-9 items-center justify-center border border-border text-primary transition-colors group-hover:border-primary">
              <svg viewBox="0 0 16 16" className="size-4" aria-hidden>
                <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="1.6" />
              </svg>
            </div>
            <h3 className="mt-6 text-lg font-semibold">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.body}</p>
          </Cell>
        ))}
      </GridCells>
    </Section>
  );
}

function Confidence() {
  const score = Math.round(
    (CONFIDENCE_SIGNALS.reduce((sum, s) => sum + s.value, 0) / CONFIDENCE_SIGNALS.length) * 100,
  );
  return (
    <Section id="confidence">
      <div className="grid gap-12 lg:grid-cols-2 lg:gap-16">
        <SectionHeading
          index="04"
          eyebrow="Confidence scoring"
          title="A score built from evidence, not vibes."
          description="Most tools ask the model how sure it is. We measure it instead: four independent signals, combined with thresholds your team controls. Below your threshold, nothing is generated."
        />
        <div className="border border-border bg-surface-solid">
          <div className="flex items-baseline justify-between border-b border-border px-6 py-5">
            <p className="text-sm text-muted-foreground">Confidence</p>
            <p className="text-4xl font-semibold text-approved tabular-nums">{score}</p>
          </div>
          <ul>
            {CONFIDENCE_SIGNALS.map((s) => (
              <li key={s.label} className="border-b border-border px-6 py-4 last:border-b-0">
                <div className="flex items-center justify-between text-sm">
                  <span>{s.label}</span>
                  <span className="font-mono text-muted-foreground">{s.value.toFixed(2)}</span>
                </div>
                <div className="mt-2 h-1 overflow-hidden bg-muted">
                  <div className="h-full bg-primary" style={{ width: `${s.value * 100}%` }} />
                </div>
                <p className="mt-2 text-xs text-subtle-foreground">{s.note}</p>
              </li>
            ))}
          </ul>
          <div className="grid grid-cols-3 border-t border-border font-mono text-xs">
            <p className="border-r border-border px-4 py-3 text-manual">&lt; 50 manual</p>
            <p className="border-r border-border px-4 py-3 text-review">50–79 review</p>
            <p className="px-4 py-3 text-approved">80+ ready</p>
          </div>
        </div>
      </div>
    </Section>
  );
}

function Testimonials() {
  return (
    <Section bleed>
      <div className="px-6 pt-20 pb-12 sm:px-10 lg:pt-24">
        <SectionHeading index="05" eyebrow="Customers" title="Security teams that stopped dreading the spreadsheet." />
      </div>
      <GridCells className="border-t border-border md:grid-cols-2 lg:grid-cols-3">
        {TESTIMONIALS.map((t) => (
          <Cell key={t.name} className="flex flex-col justify-between gap-8">
            <blockquote className="text-pretty text-foreground">&ldquo;{t.quote}&rdquo;</blockquote>
            <figcaption className="flex items-center gap-3">
              <span className="flex size-10 items-center justify-center border border-border bg-surface-raised text-sm font-semibold text-primary">
                {t.name
                  .split(" ")
                  .map((p) => p[0])
                  .join("")}
              </span>
              <span className="text-sm">
                <span className="block font-medium">{t.name}</span>
                <span className="text-muted-foreground">
                  {t.role}, {t.company}
                </span>
              </span>
            </figcaption>
          </Cell>
        ))}
      </GridCells>
    </Section>
  );
}

function Comparison() {
  return (
    <Section>
      <SectionHeading
        index="06"
        eyebrow="Why not just use a chatbot?"
        title="Plausible isn't the same as true."
      />
      <div className="mt-12 overflow-x-auto border border-border">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-surface-solid">
              <th className="w-1/4 px-6 py-4 font-medium text-muted-foreground" />
              {COMPARISON.columns.map((c, i) => (
                <th
                  key={c}
                  className={i === 1 ? "px-6 py-4 font-semibold text-primary" : "px-6 py-4 font-medium text-muted-foreground"}
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {COMPARISON.rows.map((r) => (
              <tr key={r.label} className="border-b border-border last:border-b-0">
                <th scope="row" className="px-6 py-4 font-medium">
                  {r.label}
                </th>
                <td className="px-6 py-4 text-subtle-foreground">{r.values[0]}</td>
                <td className="px-6 py-4">{r.values[1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Security() {
  return (
    <Section id="security" bleed>
      <div className="grid lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div className="border-b border-border px-6 py-20 sm:px-10 lg:border-r lg:border-b-0 lg:py-24">
          <SectionHeading
            index="07"
            eyebrow="Security"
            title="A security product that holds itself to the questionnaire."
            description="Your evidence is the most sensitive file set your company has. We treat it that way."
          />
        </div>
        <GridCells className="sm:grid-cols-2">
          {SECURITY_POINTS.map((p) => (
            <Cell key={p.title}>
              <h3 className="font-semibold">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{p.body}</p>
            </Cell>
          ))}
        </GridCells>
      </div>
    </Section>
  );
}

function Faq() {
  return (
    <Section id="faq">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <SectionHeading index="08" eyebrow="FAQ" title="Questions, answered. Obviously." />
        <div className="border-t border-border">
          {FAQ.map((f) => (
            <details key={f.q} className="group border-b border-border">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-6 py-5 font-medium">
                {f.q}
                <span className="font-mono text-primary transition-transform group-open:rotate-45">+</span>
              </summary>
              <p className="pb-5 text-sm leading-relaxed text-muted-foreground">{f.a}</p>
            </details>
          ))}
        </div>
      </div>
    </Section>
  );
}

function FinalCta() {
  return (
    <Section bleed>
      <div className="grid-backdrop relative overflow-hidden bg-primary px-6 py-20 text-primary-foreground sm:px-10 lg:py-28">
        <h2 className="max-w-4xl text-4xl leading-[0.95] font-semibold tracking-tight uppercase sm:text-6xl">
          Your next questionnaire is already half answered.
        </h2>
        <div className="mt-10 flex flex-wrap gap-3">
          <Link href={primaryCta.href} className={buttonClasses("inverse", "lg")}>
            {primaryCta.label.toUpperCase()}
          </Link>
          <a
            href={secondaryCta.href}
            className="inline-flex h-12 items-center border border-primary-foreground/30 px-6 font-medium hover:bg-primary-foreground/10"
          >
            {secondaryCta.label}
          </a>
        </div>
      </div>
    </Section>
  );
}

function SiteFooter() {
  const columns = [
    { title: "Product", links: ["Live demo", "How it works", "Confidence", "Pricing"] },
    { title: "Company", links: ["About", "Blog", "Careers", "Contact"] },
    { title: "Trust", links: ["Security", "Privacy", "Terms", "Status"] },
  ];
  return (
    <footer className="border-t border-border">
      <div className="mx-auto grid max-w-7xl gap-12 border-x border-border px-6 py-16 sm:px-10 md:grid-cols-[2fr_1fr_1fr_1fr]">
        <div>
          <BrandMark />
          <p className="mt-4 max-w-xs text-sm text-muted-foreground">
            Security questionnaires answered from your own evidence, with citations.
          </p>
        </div>
        {columns.map((c) => (
          <div key={c.title}>
            <p className="font-mono text-xs tracking-widest text-subtle-foreground uppercase">{c.title}</p>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              {c.links.map((l) => (
                <li key={l}>
                  <span className="cursor-default hover:text-foreground">{l}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="mx-auto max-w-7xl border-x border-t border-border px-6 py-6 font-mono text-xs text-subtle-foreground sm:px-10">
        © 2026 {BRAND.name}. Placeholder content for design review.
      </div>
    </footer>
  );
}
