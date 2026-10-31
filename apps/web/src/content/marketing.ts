// Landing page copy. Edit text here, not in the components.
// PLACEHOLDER: stats, logos and testimonials are dummy content for the design.
// Replace them with real, verifiable customer data before launch.

import { BRAND } from "@/config/brand";

export const NAV_LINKS = [
  { href: "#demo", label: "Live demo" },
  { href: "#how", label: "How it works" },
  { href: "#confidence", label: "Confidence" },
  { href: "#security", label: "Security" },
  { href: "#faq", label: "FAQ" },
] as const;

export const FRAMEWORKS = ["SOC 2", "CAIQ", "SIG Lite", "SIG Core", "HECVAT", "ISO 27001", "Custom"];

export const LOGOS = ["Northwind", "Globex", "Initech", "Acme Health", "Umbrella Labs", "Vandelay"];

export const STATS = [
  { value: "80%", label: "of questions drafted with citations on the first pass" },
  { value: "6 min", label: "median time to a reviewable questionnaire" },
  { value: "0", label: "answers generated without supporting evidence" },
  { value: "100%", label: "of approved answers reused automatically next time" },
];

export const STEPS = [
  {
    title: "Upload your evidence",
    body: "Policies, SOC 2 reports and past questionnaires in PDF, DOCX or XLSX. We index every page, so citations point to the exact spot.",
  },
  {
    title: "Drop in the questionnaire",
    body: "Spreadsheets, Word files, PDFs, even scans. Every question is extracted and mapped back to its original cell.",
  },
  {
    title: "Review drafts, not blank cells",
    body: "Each answer arrives with sources and a confidence score. Questions without evidence are flagged for a human, never guessed.",
  },
  {
    title: "Export in the original format",
    body: "Answers land in the same file, layout and columns your customer sent. Approved answers go into your library for next time.",
  },
];

export const FEATURES = [
  {
    title: "Page-level citations",
    body: "Every claim links to the document, page and section it came from. One click opens the source.",
  },
  {
    title: "Refuses to guess",
    body: "When retrieval finds nothing strong enough, the question is marked “Needs manual answer” and no AI text is produced.",
  },
  {
    title: "Confidence you can audit",
    body: "Scores combine retrieval strength, a reranker, library agreement and a claim-by-claim evidence check. Not the model’s opinion of itself.",
  },
  {
    title: "Answer Library",
    body: "Approved answers are reused on future questionnaires before any new drafting. Your team’s best answers compound.",
  },
  {
    title: "Original-format export",
    body: "XLSX, DOCX and CSV come back in the layout they arrived in, ready to send.",
  },
  {
    title: "Roles and audit trail",
    body: "Owners, editors and viewers. Every approval is recorded with who, what and when.",
  },
];

export const CONFIDENCE_SIGNALS = [
  { label: "Retrieval similarity", value: 0.86, note: "How closely the best passages match the question" },
  { label: "Reranker score", value: 0.91, note: "A second model re-orders candidates by relevance" },
  { label: "Evidence check", value: 1.0, note: "Each claim is verified against only the passages it cites" },
  { label: "Library agreement", value: 0.95, note: "Consistency with answers your team already approved" },
];

export const SECURITY_POINTS = [
  {
    title: "Tenant isolation in the database",
    body: "Row-level security in Postgres means one customer’s data can’t be read by another, even if application code has a bug. Covered by automated tests.",
  },
  {
    title: "Never used for training",
    body: "Your documents and answers are processed to serve you only. They are not used to train any model.",
  },
  {
    title: "Encrypted, signed, logged",
    body: "Files are encrypted at rest and served with short-lived signed links. Approvals are written to an append-only audit log.",
  },
  {
    title: "No customer data in logs",
    body: "Logging is allow-list only: ids, counts and timings. Document text and questions never reach log storage.",
  },
];

export const TESTIMONIALS = [
  {
    quote:
      "The first tool where I trust the drafts, because I can click straight to the page it came from. Review time dropped from days to an afternoon.",
    name: "Priya Raman",
    role: "Head of Security",
    company: "Northwind Analytics",
  },
  {
    quote:
      "What sold us was that it leaves questions blank when our docs don’t cover them. That’s exactly what an auditor wants.",
    name: "Marcus Bell",
    role: "GRC Lead",
    company: "Globex Cloud",
  },
  {
    quote:
      "Our sales engineers stopped forwarding spreadsheets to security. They upload, review the yellow ones, export, done.",
    name: "Elena Sokolova",
    role: "VP Sales Engineering",
    company: "Initech",
  },
  {
    quote:
      "The confidence score actually means something. When it says 90+, the citations hold up every time we spot-check.",
    name: "David Okafor",
    role: "Security Engineer",
    company: "Acme Health",
  },
  {
    quote:
      "HECVATs used to be a two-week project. The library carries most of it now, and exports land back in the university’s template.",
    name: "Hannah Lindqvist",
    role: "Compliance Manager",
    company: "Umbrella Labs",
  },
  {
    quote: "Setup took an hour: upload the SOC 2 report and policy folder, and the next questionnaire was mostly drafted.",
    name: "Tom Whitaker",
    role: "CTO",
    company: "Vandelay Systems",
  },
];

export const COMPARISON = {
  columns: ["Generic AI chat", BRAND.name],
  rows: [
    { label: "Sources", values: ["Whatever you paste in", "Your indexed documents, per organization"] },
    { label: "No evidence found", values: ["Writes a plausible answer anyway", "Flags for a human, generates nothing"] },
    { label: "Citations", values: ["Rare, unverifiable", "Document + page + section, clickable"] },
    { label: "Confidence", values: ["None", "0–100 with the reasons behind it"] },
    { label: "Output", values: ["Text to copy and paste", "The original file, filled in"] },
    { label: "Memory", values: ["Starts over each chat", "Approved answers reused automatically"] },
  ],
};

export const FAQ = [
  {
    q: "What happens when my documents don’t cover a question?",
    a: "Nothing is generated. If the best evidence falls below your organization’s threshold, the question is marked “Needs manual answer” so a person writes it. You can tune the thresholds.",
  },
  {
    q: "Which questionnaire formats do you support?",
    a: "Excel, CSV and Word files today, with PDF and scanned questionnaires extracted via layout-aware OCR. Exports go back into the original format where the file allows it.",
  },
  {
    q: "Is our data used to train AI models?",
    a: "No. Your data is only used to answer your questionnaires. Model providers process requests under terms that exclude training on customer data.",
  },
  {
    q: "How is the confidence score calculated?",
    a: "It combines retrieval similarity, a reranker score, agreement with your approved Answer Library, and a separate check that each claim is supported by the passages it cites.",
  },
  {
    q: "Can different people review different sections?",
    a: "Yes. Owners and editors can approve answers, viewers can read. Every approval is recorded in the audit log.",
  },
];
