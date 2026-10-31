"use client";

import { useEffect, useState } from "react";

import { CitationChip, type Citation } from "@/components/answer/citation-chip";
import { ConfidenceMeter } from "@/components/answer/confidence-meter";
import { Badge, type Tone } from "@/components/ui/badge";
import { cn } from "@/lib/cn";

type Sample = {
  question: string;
  outcome: { tone: Tone; label: string };
  topSimilarity: number;
  answer?: string;
  citations?: Citation[];
  score?: number;
  reason?: string;
  signals?: { label: string; value: number }[];
};

// Scripted examples that mirror the real pipeline's decisions.
const SAMPLES: Sample[] = [
  {
    question: "Is customer data encrypted at rest?",
    outcome: { tone: "approved", label: "Ready to approve" },
    topSimilarity: 0.88,
    answer:
      "Yes. All customer data is encrypted at rest using AES-256. Encryption keys are managed in AWS KMS and rotated annually.",
    citations: [
      { documentName: "Encryption Policy", page: 3, heading: "2.1 Data at rest" },
      { documentName: "SOC 2 Type II Report", page: 37, heading: "CC6.1" },
    ],
    score: 94,
    reason: "2/2 claims supported · matches an approved library answer",
    signals: [
      { label: "Retrieval", value: 0.88 },
      { label: "Reranker", value: 0.93 },
      { label: "Evidence check", value: 1 },
      { label: "Library", value: 0.96 },
    ],
  },
  {
    question: "Is MFA enforced for all workforce accounts?",
    outcome: { tone: "library", label: "Reused from library" },
    topSimilarity: 0.97,
    answer:
      "Yes. MFA is enforced through our identity provider for all employees and contractors, including access to production systems.",
    citations: [{ documentName: "Access Control Policy", page: 4, heading: "3.2 Authentication" }],
    score: 98,
    reason: "Near-exact match to an answer approved by Priya R. on 12 Sep",
    signals: [
      { label: "Retrieval", value: 0.97 },
      { label: "Reranker", value: 0.95 },
      { label: "Evidence check", value: 1 },
      { label: "Library", value: 0.99 },
    ],
  },
  {
    question: "Do you perform annual third-party penetration tests?",
    outcome: { tone: "review", label: "Needs review" },
    topSimilarity: 0.74,
    answer:
      "Yes. An independent firm performs penetration testing annually, and findings are tracked to remediation.",
    citations: [{ documentName: "SOC 2 Type II Report", page: 41, heading: "CC4.1" }],
    score: 68,
    reason: "Supported, but the cited report period ended Mar 2026",
    signals: [
      { label: "Retrieval", value: 0.74 },
      { label: "Reranker", value: 0.71 },
      { label: "Evidence check", value: 0.5 },
      { label: "Library", value: 0 },
    ],
  },
  {
    question: "Do you support customer-managed encryption keys (BYOK)?",
    outcome: { tone: "manual", label: "Needs manual answer" },
    topSimilarity: 0.31,
  },
];

const THRESHOLD = 0.55;
const STAGES = ["Searching 42 documents", "Reranking candidate passages", "Drafting from evidence", "Checking every claim"];

export function LiveDemo() {
  const [selected, setSelected] = useState(0);
  const [stage, setStage] = useState(0);
  const sample = SAMPLES[selected];
  const gated = sample.topSimilarity < THRESHOLD;
  // Gated questions stop after reranking: nothing is drafted.
  const lastStage = gated ? 2 : STAGES.length;
  const done = stage >= lastStage;

  useEffect(() => {
    if (done) return;
    const timer = setTimeout(() => setStage((s) => s + 1), 550);
    return () => clearTimeout(timer);
  }, [stage, done]);

  function choose(index: number) {
    setSelected(index);
    setStage(0);
  }

  return (
    <div className="grid gap-px bg-border lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      {/* Question list */}
      <div className="bg-background">
        <p className="border-b border-border px-6 py-3 font-mono text-xs tracking-widest text-subtle-foreground uppercase">
          vendor-assessment.xlsx · 4 of 212
        </p>
        <ul>
          {SAMPLES.map((s, i) => (
            <li key={s.question}>
              <button
                type="button"
                onClick={() => choose(i)}
                aria-pressed={i === selected}
                className={cn(
                  "flex w-full items-start gap-3 border-b border-border px-6 py-4 text-left text-sm transition-colors",
                  i === selected ? "bg-surface-raised text-foreground" : "text-muted-foreground hover:bg-muted",
                )}
              >
                <span
                  className={cn(
                    "mt-1.5 size-1.5 shrink-0 rounded-full",
                    i === selected ? "bg-primary" : "bg-border-strong",
                  )}
                />
                {s.question}
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Pipeline + result */}
      <div className="flex min-h-[420px] flex-col bg-surface-solid p-6 sm:p-8">
        <p className="text-lg font-medium">{sample.question}</p>

        <ol className="mt-5 space-y-2 font-mono text-xs">
          {STAGES.map((label, i) => {
            const skipped = gated && i >= 2;
            const state = skipped ? "skipped" : i < stage ? "done" : i === stage && !done ? "running" : "idle";
            return (
              <li
                key={label}
                className={cn(
                  "flex items-center gap-3",
                  state === "idle" && "text-subtle-foreground",
                  state === "skipped" && "text-subtle-foreground line-through",
                  state === "running" && "text-primary",
                  state === "done" && "text-muted-foreground",
                )}
              >
                <span className="w-4 text-center">
                  {state === "done" ? "✓" : state === "running" ? "›" : state === "skipped" ? "–" : "·"}
                </span>
                {label}
                {i === 1 && state === "done" && (
                  <span className={gated ? "text-manual" : "text-approved"}>
                    top match {sample.topSimilarity.toFixed(2)} {gated ? "<" : "≥"} {THRESHOLD}
                  </span>
                )}
              </li>
            );
          })}
        </ol>

        {done && (
          <div key={selected} className="animate-fade-up mt-6 flex-1 border-t border-border pt-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Badge tone={sample.outcome.tone}>{sample.outcome.label}</Badge>
              {sample.score !== undefined && <ConfidenceMeter score={sample.score} />}
            </div>

            {gated ? (
              <div className="mt-5 rounded-md border border-dashed border-manual/40 bg-manual-bg p-4 text-sm">
                <p className="font-medium text-manual">No answer generated.</p>
                <p className="mt-1 text-muted-foreground">
                  Nothing in your documents supports this strongly enough, so it goes to a person
                  instead of getting a guess. Once someone writes and approves it, it is reused from
                  the library next time.
                </p>
              </div>
            ) : (
              <>
                <p className="mt-5 text-sm leading-relaxed text-foreground">{sample.answer}</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {sample.citations?.map((c) => (
                    <CitationChip key={`${c.documentName}${c.page}`} {...c} />
                  ))}
                </div>
                <p className="mt-4 text-xs text-muted-foreground">{sample.reason}</p>
                <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
                  {sample.signals?.map((s) => (
                    <div key={s.label}>
                      <dt className="text-xs text-subtle-foreground">{s.label}</dt>
                      <dd className="mt-1.5 h-1 overflow-hidden rounded-full bg-muted">
                        <div className="h-full bg-primary" style={{ width: `${s.value * 100}%` }} />
                      </dd>
                    </div>
                  ))}
                </dl>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
