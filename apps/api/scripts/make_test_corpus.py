"""Generate the QAutos test corpus: evidence documents and questionnaires.

Everything is about one fictional vendor, Brightline Health Analytics, so the
questionnaires can be answered from the evidence. Each questionnaire gets an
answer key (the questions it really contains) for measuring extraction.

Usage (from apps/api):
    uv run python scripts/make_test_corpus.py                # -> D:/Prods/Qautos-test
    uv run python scripts/make_test_corpus.py --out some/dir

All companies, people and numbers are invented.
"""

import argparse
import csv
import io
import json
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

import pymupdf
from docx import Document
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Font

VENDOR = "Brightline Health Analytics"
DEFAULT_OUT = Path(__file__).resolve().parents[4] / "Qautos-test"

# --- Question bank -------------------------------------------------------------------
# (domain, CAIQ-style id, question). Questionnaires draw from this in different formats.
BANK: list[tuple[str, str, str]] = [
    (
        "Governance",
        "GRC-01.1",
        "Do you have a documented information security program approved by executive management?",
    ),
    ("Governance", "GRC-02.1", "Is the information security policy reviewed at least annually?"),
    (
        "Governance",
        "GRC-03.1",
        "Have you designated a named individual responsible for information security, such as a CISO?",
    ),
    (
        "Governance",
        "GRC-04.1",
        "Do you maintain a risk register and perform a formal risk assessment at least annually?",
    ),
    (
        "Audit & Assurance",
        "A&A-01.1",
        "Do you undergo an independent SOC 2 Type II audit at least annually?",
    ),
    (
        "Audit & Assurance",
        "A&A-02.1",
        "Were any exceptions noted in your most recent SOC 2 report?",
    ),
    (
        "Audit & Assurance",
        "A&A-03.1",
        "Do you hold any other certifications such as ISO 27001 or HITRUST?",
    ),
    (
        "Identity & Access",
        "IAM-01.1",
        "Is multi-factor authentication required for all workforce access to production systems?",
    ),
    (
        "Identity & Access",
        "IAM-02.1",
        "Do you use single sign-on for employee access to corporate applications?",
    ),
    ("Identity & Access", "IAM-03.1", "How often are user access rights reviewed?"),
    (
        "Identity & Access",
        "IAM-04.1",
        "How quickly is access revoked when an employee leaves the company?",
    ),
    (
        "Identity & Access",
        "IAM-05.1",
        "Is privileged access to production granted just in time and logged?",
    ),
    ("Identity & Access", "IAM-06.1", "Are shared or generic administrator accounts prohibited?"),
    ("Encryption", "CEK-01.1", "Is customer data encrypted at rest, and with which algorithm?"),
    ("Encryption", "CEK-02.1", "Is customer data encrypted in transit using TLS 1.2 or higher?"),
    ("Encryption", "CEK-03.1", "Where are encryption keys stored and how often are they rotated?"),
    ("Encryption", "CEK-04.1", "Can customers bring their own encryption keys?"),
    ("Data Protection", "DSP-01.1", "Do you classify data according to its sensitivity?"),
    ("Data Protection", "DSP-02.1", "In which countries or regions is customer data stored?"),
    ("Data Protection", "DSP-03.1", "How long is customer data retained after the contract ends?"),
    ("Data Protection", "DSP-04.1", "Can you provide a certificate of data deletion on request?"),
    ("Data Protection", "DSP-05.1", "Do you use customer data to train machine learning models?"),
    ("Logging & Monitoring", "LOG-01.1", "Are security events centrally logged and monitored?"),
    ("Logging & Monitoring", "LOG-02.1", "How long are audit and security logs retained?"),
    ("Logging & Monitoring", "LOG-03.1", "Is your security operations function staffed 24x7?"),
    ("Incident Response", "SEF-01.1", "Do you have a documented incident response plan?"),
    ("Incident Response", "SEF-02.1", "How often is the incident response plan tested?"),
    (
        "Incident Response",
        "SEF-03.1",
        "Within what timeframe will customers be notified of a security incident affecting their data?",
    ),
    (
        "Incident Response",
        "SEF-04.1",
        "Have you experienced a data breach in the last three years?",
    ),
    (
        "Business Continuity",
        "BCR-01.1",
        "What are your recovery time and recovery point objectives?",
    ),
    ("Business Continuity", "BCR-02.1", "Are backups encrypted and stored in a separate location?"),
    ("Business Continuity", "BCR-03.1", "How often are backup restores tested?"),
    ("Business Continuity", "BCR-04.1", "When was the business continuity plan last tested?"),
    (
        "Secure Development",
        "AIS-01.1",
        "Do all code changes require peer review before deployment?",
    ),
    (
        "Secure Development",
        "AIS-02.1",
        "Do you perform static code analysis and dependency vulnerability scanning?",
    ),
    (
        "Secure Development",
        "AIS-03.1",
        "Is an independent penetration test performed at least annually?",
    ),
    (
        "Secure Development",
        "AIS-04.1",
        "What are your remediation timelines for critical and high vulnerabilities?",
    ),
    (
        "Vendor Management",
        "STA-01.1",
        "Do you assess the security of your subprocessors before onboarding?",
    ),
    ("Vendor Management", "STA-02.1", "Do you publish or provide a list of subprocessors?"),
    (
        "Vendor Management",
        "STA-03.1",
        "Will you notify customers before adding a new subprocessor?",
    ),
    ("Human Resources", "HRS-01.1", "Do employees undergo background checks before hire?"),
    (
        "Human Resources",
        "HRS-02.1",
        "Do employees complete security awareness training at least annually?",
    ),
    ("Human Resources", "HRS-03.1", "Do employees sign confidentiality agreements?"),
    ("Infrastructure", "IVS-01.1", "Which cloud provider hosts the production environment?"),
    (
        "Infrastructure",
        "IVS-02.1",
        "Is the production environment logically separated from development and test?",
    ),
    (
        "Infrastructure",
        "IVS-03.1",
        "Are production systems hardened against a documented baseline?",
    ),
    (
        "Infrastructure",
        "TVM-01.1",
        "How frequently do you scan your infrastructure for vulnerabilities?",
    ),
    ("Privacy", "PRV-01.1", "Will you sign a Business Associate Agreement under HIPAA?"),
    ("Privacy", "PRV-02.1", "Do you support data subject requests under GDPR and CCPA?"),
    (
        "Privacy",
        "PRV-03.1",
        "Describe how protected health information is segregated between customers.",
    ),
]
DESCRIBE = [
    "Describe your process for onboarding and offboarding employees.",
    "Provide an overview of your network architecture and segmentation.",
    "Explain how you detect and respond to unauthorized access attempts.",
    "List the third parties that process customer data on your behalf.",
]


def pick(domains: set[str] | None = None, limit: int | None = None) -> list[tuple[str, str, str]]:
    items = [b for b in BANK if domains is None or b[0] in domains]
    return items[:limit] if limit else items


# --- Writers -------------------------------------------------------------------------


class PdfWriter:
    """Flowing text PDF with headings, page breaks, running header and footer."""

    LEFT, RIGHT, TOP, BOTTOM = 72, 540, 80, 770

    def __init__(self, header: str | None = None) -> None:
        self.doc = pymupdf.open()
        self.header = header
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.doc.new_page()
        self.y = float(self.TOP)

    def text(self, text: str, *, size: float = 10.5, bold: bool = False, gap: float = 6) -> None:
        width = int((self.RIGHT - self.LEFT) / (size * 0.5))
        lines = textwrap.wrap(text, width=width) or [""]
        height = len(lines) * size * 1.35
        if self.y + height > self.BOTTOM:
            self._new_page()
        for line in lines:
            self.page.insert_text(
                (self.LEFT, self.y + size), line, fontsize=size, fontname="hebo" if bold else "helv"
            )
            self.y += size * 1.35
        self.y += gap

    def heading(self, text: str, level: int = 1) -> None:
        if self.y > self.BOTTOM - 80:
            self._new_page()
        self.y += 6
        self.text(text, size={0: 20, 1: 15, 2: 12.5}[level], bold=True, gap=8)

    def bytes(self) -> bytes:
        pages = self.doc.page_count
        for i in range(pages):
            page = self.doc[i]
            if self.header:
                page.insert_text((72, 40), self.header, fontsize=8)
            page.insert_text((470, 805), f"Page {i + 1} of {pages}", fontsize=8)
        return self.doc.tobytes()


def write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    if __name__ == "__main__":
        print(f"  {path.relative_to(path.parents[1])}")


def docx_bytes(document: Document) -> bytes:  # type: ignore[valid-type]
    out = io.BytesIO()
    document.save(out)  # type: ignore[attr-defined]
    return out.getvalue()


def xlsx_bytes(workbook: Workbook) -> bytes:
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


def policy_pdf(title: str, sections: list[tuple[str, list[str]]], *, subtitle: str = "") -> bytes:
    pdf = PdfWriter(header=f"{VENDOR} - Confidential")
    pdf.heading(title, 0)
    if subtitle:
        pdf.text(subtitle, size=10, gap=14)
    for heading, paragraphs in sections:
        pdf.heading(heading, 1 if not heading[:1].isdigit() or heading.count(".") < 2 else 2)
        for paragraph in paragraphs:
            pdf.text(paragraph)
    return pdf.bytes()


def policy_docx(
    title: str, sections: list[tuple[str, list[str]]], table: list[list[str]] | None = None
) -> bytes:
    document = Document()
    document.add_heading(title, level=0)
    for heading, paragraphs in sections:
        document.add_heading(heading, level=1)
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
    if table:
        grid = document.add_table(rows=0, cols=len(table[0]))
        for row in table:
            cells = grid.add_row().cells
            for cell, value in zip(cells, row, strict=True):
                cell.text = value
    return docx_bytes(document)


# --- Evidence ------------------------------------------------------------------------

EVIDENCE: dict[str, tuple[str, list[tuple[str, list[str]]]]] = {
    "Brightline Information Security Policy.docx": (
        "Information Security Policy",
        [
            (
                "1. Purpose",
                [
                    f"This policy establishes how {VENDOR} protects the confidentiality, integrity and availability of customer data, including protected health information (PHI). It applies to all employees, contractors and systems."
                ],
            ),
            (
                "2. Governance",
                [
                    "The information security program is owned by the Chief Information Security Officer (CISO), Dana Whitfield, and approved by the executive leadership team. This policy is reviewed at least annually and after any significant change.",
                    "A risk register is maintained by the security team. A formal risk assessment is performed annually and reviewed by the executive risk committee.",
                ],
            ),
            (
                "3. Access Control",
                [
                    "Workforce access to corporate applications uses single sign-on through Okta. Phishing-resistant multi-factor authentication (WebAuthn security keys) is required for all workforce access, including all access to production systems.",
                    "Shared or generic administrator accounts are prohibited. Privileged production access is granted just in time for a maximum of four hours through an approved request, and every session is logged.",
                ],
            ),
            (
                "4. Human Resources Security",
                [
                    "All employees undergo criminal background checks before hire, where permitted by law, and sign confidentiality agreements as part of their employment contract.",
                    "Security awareness and HIPAA privacy training is completed at hire and annually thereafter. Monthly phishing simulations are run for all staff.",
                ],
            ),
            (
                "5. Data Classification",
                [
                    "Data is classified as Public, Internal, Confidential or Restricted. Customer data and PHI are Restricted and receive the strongest controls."
                ],
            ),
            (
                "6. Customer Data and Machine Learning",
                [
                    "Customer data is never used to train machine learning models that are shared across customers. Models are trained only on a customer's own data, inside that customer's tenant, and only when the customer enables the feature."
                ],
            ),
            (
                "7. Compliance",
                [
                    "Exceptions to this policy require written approval from the CISO, are recorded in the risk register and expire after at most twelve months."
                ],
            ),
        ],
    ),
    "Brightline Encryption and Key Management Standard.docx": (
        "Encryption and Key Management Standard",
        [
            (
                "Encryption at Rest",
                [
                    "All customer data at rest is encrypted with AES-256-GCM. This includes databases, object storage, backups and snapshots."
                ],
            ),
            (
                "Encryption in Transit",
                [
                    "All external connections require TLS 1.2 or higher; TLS 1.3 is preferred. TLS 1.0 and 1.1, and weak cipher suites, are disabled. Internal service-to-service traffic uses mutual TLS."
                ],
            ),
            (
                "Key Management",
                [
                    "Encryption keys are stored in AWS Key Management Service (KMS) backed by FIPS 140-2 validated hardware security modules. Customer master keys are rotated automatically every 365 days. Key usage is logged to CloudTrail.",
                    "Customer-managed keys (bring your own key) are available on the Enterprise plan through AWS KMS external key stores.",
                ],
            ),
        ],
    ),
    "Brightline Business Continuity and Disaster Recovery Plan.docx": (
        "Business Continuity and Disaster Recovery Plan",
        [
            (
                "Objectives",
                [
                    f"This plan keeps the {VENDOR} platform available through disruptions to people, facilities, suppliers or infrastructure."
                ],
            ),
            (
                "Recovery Objectives",
                [
                    "The recovery time objective (RTO) for the analytics platform is 4 hours. The recovery point objective (RPO) is 1 hour."
                ],
            ),
            (
                "Backups",
                [
                    "Production databases are backed up continuously with point-in-time recovery and daily snapshots. Backups are encrypted with AES-256 and replicated to a separate AWS account in a second region (us-west-2). Backup restores are tested quarterly."
                ],
            ),
            (
                "Testing",
                [
                    "The business continuity plan is tested annually through a full regional failover exercise. The last exercise was completed in May 2026 and met both the RTO and RPO."
                ],
            ),
        ],
    ),
    "Brightline Vendor Risk Management Policy.docx": (
        "Vendor Risk Management Policy",
        [
            (
                "Scope",
                [
                    "This policy applies to every third party (subprocessor) that stores, processes or can access customer data."
                ],
            ),
            (
                "Assessment",
                [
                    "Subprocessors are assessed before onboarding and annually thereafter. The assessment reviews their SOC 2 Type II or ISO 27001 report, a security questionnaire and the data processing agreement."
                ],
            ),
            (
                "Subprocessor List and Notice",
                [
                    "The current subprocessor list is published at trust.brightline.example/subprocessors. Customers are notified at least 30 days before a new subprocessor is added and may object."
                ],
            ),
        ],
    ),
}

PDF_EVIDENCE: dict[str, tuple[str, str, list[tuple[str, list[str]]]]] = {
    "Brightline SOC 2 Type II Report (Excerpt).pdf": (
        "SOC 2 Type II Report - Excerpt",
        "Report on Controls Relevant to Security, Availability and Confidentiality for the period June 1, 2025 to May 31, 2026. Independent service auditor: Harbor & Lane LLP (fictional).",
        [
            (
                "Section 1. Independent Service Auditor's Report",
                [
                    "In our opinion, in all material respects, the controls stated in the description were suitably designed and operated effectively throughout the period June 1, 2025 to May 31, 2026 to provide reasonable assurance that the service commitments and system requirements were achieved, based on the applicable trust services criteria.",
                    "This is an unqualified opinion.",
                ],
            ),
            (
                "Section 3. Description of the System",
                [
                    f"{VENDOR} provides a cloud analytics platform for healthcare providers. The platform is hosted on Amazon Web Services (AWS) in the us-east-1 region, with backups in us-west-2. Production, staging and development run in separate AWS accounts with no network connectivity between them.",
                    "Customer data, including PHI, is stored in the United States only. Each customer's data is stored in a separate database schema with row-level security, and is encrypted with a customer-specific data key.",
                ],
            ),
            (
                "Section 4. Tests of Controls and Results",
                [
                    "CC6.1 Logical access: multi-factor authentication is enforced for all workforce access. Tested: inspected identity provider configuration and 25 sampled logins. No exceptions noted.",
                    "CC6.2 Access reviews: user access is reviewed quarterly by system owners. Tested: inspected four quarterly reviews. No exceptions noted.",
                    "CC6.3 Termination: access is revoked within 24 hours of termination. Tested: 25 sampled terminations. One exception noted: one contractor's access was revoked after 3 days. Management response: automated deprovisioning from the HR system was implemented in March 2026.",
                    "CC7.2 Monitoring: security events are centralized in the SIEM and monitored 24x7 by the security operations team. No exceptions noted.",
                    "CC8.1 Change management: all changes require peer review and passing automated tests. No exceptions noted.",
                    "A1.2 Backups: backups are performed continuously and restores are tested quarterly. No exceptions noted.",
                ],
            ),
        ],
    ),
    "Brightline Access Control Standard.pdf": (
        "Access Control Standard",
        "Version 3.2, approved by the CISO.",
        [
            (
                "1. Authentication",
                [
                    "All workforce access uses single sign-on with phishing-resistant multi-factor authentication. Passwords, where still used, are at least 14 characters and checked against breached-password lists."
                ],
            ),
            (
                "2. Authorization",
                [
                    "Access is role-based and follows least privilege. Production access is granted just in time for up to four hours and requires a ticket."
                ],
            ),
            (
                "3. Access Reviews",
                [
                    "System owners review user access quarterly. Privileged access is reviewed monthly."
                ],
            ),
            (
                "4. Termination",
                [
                    "Access is revoked automatically when the HR system marks an employee as terminated, and in any case within 24 hours. Involuntary terminations are revoked immediately."
                ],
            ),
        ],
    ),
    "Brightline Incident Response Plan.pdf": (
        "Incident Response Plan",
        "Owned by the Security Operations team.",
        [
            (
                "1. Overview",
                [
                    "This plan defines how security incidents are detected, triaged, contained, eradicated and recovered from. Security events from all production systems are centralized in the SIEM and monitored 24x7. Security logs are retained for 13 months."
                ],
            ),
            (
                "2. Severity Levels",
                [
                    "SEV-1: confirmed compromise of customer data. SEV-2: suspected compromise or active attack. SEV-3: policy violation without data exposure."
                ],
            ),
            (
                "3. Customer Notification",
                [
                    "Affected customers are notified without undue delay and no later than 72 hours after an incident affecting their data is confirmed. For PHI, notification also follows the HIPAA Breach Notification Rule and the Business Associate Agreement."
                ],
            ),
            (
                "4. Testing",
                [
                    "The incident response plan is tested twice a year through tabletop exercises, and lessons learned are tracked to closure."
                ],
            ),
            (
                "5. History",
                [
                    "Brightline has not experienced a data breach requiring customer or regulatory notification in the last three years."
                ],
            ),
        ],
    ),
    "Brightline Data Retention and Deletion Standard.pdf": (
        "Data Retention and Deletion Standard",
        "",
        [
            (
                "1. Retention",
                [
                    "Customer data is retained for the duration of the contract. Audit and security logs are retained for 13 months."
                ],
            ),
            (
                "2. Deletion at Contract End",
                [
                    "Within 30 days after the contract ends, customer data is deleted from production systems. Backups containing the data expire within 90 days. A certificate of deletion is provided on request."
                ],
            ),
            (
                "3. Data Location",
                [
                    "Customer data is stored only in the United States (AWS us-east-1, with backups in us-west-2)."
                ],
            ),
        ],
    ),
    "Brightline Secure SDLC Policy.pdf": (
        "Secure Software Development Policy",
        "",
        [
            (
                "1. Code Review",
                [
                    "Every code change requires review and approval by a second engineer before it can be merged, enforced by branch protection."
                ],
            ),
            (
                "2. Automated Testing and Scanning",
                [
                    "The CI pipeline runs unit tests, static application security testing (SAST) and dependency vulnerability scanning on every change. Merges are blocked on critical findings."
                ],
            ),
            (
                "3. Penetration Testing",
                [
                    "An independent firm performs a penetration test of the application and infrastructure at least annually and after major releases."
                ],
            ),
            (
                "4. Vulnerability Remediation",
                [
                    "Critical vulnerabilities are remediated within 7 days, high within 30 days, medium within 90 days. Infrastructure is scanned for vulnerabilities weekly."
                ],
            ),
            (
                "5. Hardening",
                [
                    "Production hosts are built from hardened images based on CIS Benchmarks and rebuilt rather than patched in place."
                ],
            ),
        ],
    ),
    "Brightline Master Services Agreement - Security Exhibit.pdf": (
        "Exhibit B - Information Security Requirements",
        "Exhibit to the Master Services Agreement between Brightline Health Analytics and Customer.",
        [
            (
                "1. Security Program",
                [
                    "Brightline shall maintain a written information security program with administrative, technical and physical safeguards appropriate to the sensitivity of Customer Data, consistent with SOC 2 and the HIPAA Security Rule."
                ],
            ),
            (
                "2. Audit Reports",
                [
                    "Brightline shall provide its most recent SOC 2 Type II report annually upon request, under NDA."
                ],
            ),
            (
                "3. Security Incidents",
                [
                    "Brightline shall notify Customer of a Security Incident affecting Customer Data without undue delay and in any event within 72 hours of confirmation."
                ],
            ),
            (
                "4. Business Associate Agreement",
                [
                    "Where Customer Data includes PHI, the parties shall execute Brightline's standard Business Associate Agreement, which forms part of this Agreement."
                ],
            ),
            (
                "5. Return and Deletion",
                [
                    "Upon termination, Brightline shall make Customer Data available for export for 30 days and then delete it, providing written certification of deletion on request."
                ],
            ),
        ],
    ),
    "Brightline Penetration Test Summary Letter 2026.pdf": (
        "Penetration Test Summary Letter",
        "Prepared by Redline Security Partners (fictional), April 2026.",
        [
            (
                "Scope",
                [
                    "External network, web application and API of the Brightline analytics platform, tested between March 2 and March 20, 2026."
                ],
            ),
            (
                "Results",
                [
                    "No critical findings. Two high-severity findings (an IDOR in a reporting endpoint and a missing rate limit on login) were remediated and verified closed on March 31, 2026. Five medium and low findings are tracked with remediation dates."
                ],
            ),
        ],
    ),
    "Brightline HIPAA Compliance Overview.pdf": (
        "HIPAA Compliance Overview",
        "",
        [
            (
                "Business Associate",
                [
                    "Brightline acts as a Business Associate to covered entities and signs a Business Associate Agreement (BAA) with every customer that shares PHI."
                ],
            ),
            (
                "Safeguards",
                [
                    "PHI is segregated per customer in separate database schemas with row-level security, encrypted with customer-specific keys, and accessible only to authorized personnel with just-in-time access."
                ],
            ),
            (
                "Privacy Requests",
                [
                    "Brightline supports customers in fulfilling data subject and patient access requests, including requests under GDPR and CCPA, within 10 business days."
                ],
            ),
        ],
    ),
}


def build_evidence(out: Path) -> None:
    target = out / "evidence"
    for name, (title, sections) in EVIDENCE.items():
        write(target / name, policy_docx(title, sections))
    for name, (title, subtitle, sections) in PDF_EVIDENCE.items():
        write(target / name, policy_pdf(title, sections, subtitle=subtitle))

    sow = Document()
    sow.add_heading("Statement of Work - Implementation Services", level=0)
    for heading, text in [
        (
            "1. Parties",
            f"This Statement of Work is entered into between {VENDOR} and Acme Regional Hospital under the Master Services Agreement.",
        ),
        (
            "2. Scope of Services",
            "Brightline will configure the analytics platform, integrate the customer's EHR via HL7 FHIR, and train up to 20 customer users.",
        ),
        (
            "3. Security Responsibilities",
            "All Brightline personnel accessing customer systems will use customer-issued accounts with multi-factor authentication. No PHI will be stored on Brightline laptops. Data transfers use SFTP or HTTPS with TLS 1.2 or higher.",
        ),
        ("4. Timeline", "Implementation completes within 12 weeks of the kickoff date."),
    ]:
        sow.add_heading(heading, level=1)
        sow.add_paragraph(text)
    write(target / "Brightline Statement of Work - Implementation Services.docx", docx_bytes(sow))

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Subprocessors"
    sheet.append(["Subprocessor", "Purpose", "Data processed", "Location", "Assurance"])
    for row in [
        (
            "Amazon Web Services",
            "Cloud hosting",
            "All customer data",
            "United States",
            "SOC 2 Type II, ISO 27001",
        ),
        (
            "Okta",
            "Workforce identity",
            "Employee identities only",
            "United States",
            "SOC 2 Type II",
        ),
        (
            "Datadog",
            "Infrastructure monitoring",
            "System metrics, no PHI",
            "United States",
            "SOC 2 Type II",
        ),
        (
            "Zendesk",
            "Customer support",
            "Support tickets, no PHI",
            "United States",
            "SOC 2 Type II",
        ),
    ]:
        sheet.append(list(row))
    write(target / "Brightline Subprocessor List.xlsx", xlsx_bytes(workbook))

    # Last year's answered SIG Lite: past answers are evidence too.
    answers = {
        "IAM-01.1": "Yes. Phishing-resistant MFA (WebAuthn) is required for all workforce access.",
        "IAM-03.1": "Quarterly by system owners; privileged access monthly.",
        "CEK-01.1": "Yes, AES-256-GCM with keys in AWS KMS.",
        "DSP-03.1": "Deleted from production within 30 days of contract end; backups expire within 90 days.",
        "SEF-03.1": "Within 72 hours of confirmation.",
        "BCR-01.1": "RTO 4 hours, RPO 1 hour.",
        "AIS-03.1": "Yes, annually by an independent firm. Latest test completed March 2026.",
        "HRS-02.1": "Yes, at hire and annually, plus monthly phishing simulations.",
    }
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "SIG Lite 2025"
    sheet.append(["Ques Num", "Question/Request", "Response", "Additional Information"])
    for _domain, ref, question in BANK:
        if ref in answers:
            sheet.append([ref, question, answers[ref], ""])
    write(
        target / "Brightline Prior Questionnaire Answers (SIG Lite 2025).xlsx", xlsx_bytes(workbook)
    )


# --- Questionnaires --------------------------------------------------------------------


def key(
    out: Path, filename: str, questions: list[str], note: str = "", mapping: dict | None = None
) -> None:
    record = {"file": filename, "note": note, "questions": questions}
    if mapping:
        record["user_mapping"] = mapping  # what the user would choose when asked
    write(out / "answer-keys" / f"{filename}.json", json.dumps(record, indent=2))


def caiq_xlsx(out: Path) -> None:
    name = "CAIQ v4 Lite - Acme Regional Hospital.xlsx"
    workbook = Workbook()
    intro = workbook.active
    assert intro is not None
    intro.title = "Instructions"
    for line in [
        "Consensus Assessments Initiative Questionnaire (CAIQ) v4 - Lite",
        "Please answer every question in the CAIQ tab with Yes, No or N/A, and add comments where helpful.",
        "Return the completed questionnaire to vendor-risk@acme-hospital.example within 10 business days.",
    ]:
        intro.append([line])
    sheet = workbook.create_sheet("CAIQ")
    sheet.append(["Acme Regional Hospital - Vendor Assessment"])
    sheet.append([])
    sheet.append(["Question ID", "Question", "CSP CAIQ Answer", "CSP Implementation Description"])
    for cell in sheet[3]:
        cell.font = Font(bold=True)
    expected: list[str] = []
    current = None
    for domain, ref, question in pick(
        {
            "Audit & Assurance",
            "Identity & Access",
            "Encryption",
            "Data Protection",
            "Logging & Monitoring",
            "Incident Response",
            "Business Continuity",
        }
    ):
        if domain != current:
            sheet.append([domain])  # section row
            current = domain
        sheet.append([ref, question, "", ""])
        expected.append(question)
    write(out / "questionnaires" / name, xlsx_bytes(workbook))
    key(out, name, expected, "Instructions sheet must be ignored; domain rows are sections.")


def sig_xlsx(out: Path) -> None:
    name = "SIG Lite 2026 - Excerpt.xlsx"
    workbook = Workbook()
    workbook.remove(workbook.active)  # type: ignore[arg-type]
    expected: list[str] = []
    tabs = [
        ("A. Risk Management", {"Governance"}),
        ("B. Access Control", {"Identity & Access"}),
        ("C. Development", {"Secure Development", "Infrastructure"}),
    ]
    for tab, domains in tabs:
        sheet = workbook.create_sheet(tab)
        sheet.append(["Ques Num", "Question/Request", "Response", "Additional Information"])
        for i, (_d, _ref, question) in enumerate(pick(domains), start=1):
            sheet.append([f"{tab[0]}.{i}", question, "", ""])
            expected.append(question)
    write(out / "questionnaires" / name, xlsx_bytes(workbook))
    key(out, name, expected, "Three tabs, one header row each.")


def hecvat_xlsx(out: Path) -> None:
    name = "HECVAT Lite (sample) - State University.xlsx"
    workbook = Workbook()
    summary = workbook.active
    assert summary is not None
    summary.title = "Summary"
    summary.append(["Vendor name", VENDOR])
    summary.append(["Product", "Analytics Platform"])
    sheet = workbook.create_sheet("HECVAT - Lite")
    sheet.append(["Higher Education Community Vendor Assessment Toolkit - Lite (sample)"])
    sheet.append(["Question ID", "Question", "Vendor Answer", "Additional Info"])
    expected: list[str] = []
    for i, (_d, _ref, question) in enumerate(
        pick({"Data Protection", "Privacy", "Human Resources", "Vendor Management"}), start=1
    ):
        sheet.append([f"HLDP-{i:02d}", question, "", ""])
        expected.append(question)
    write(out / "questionnaires" / name, xlsx_bytes(workbook))
    key(out, name, expected, "Summary sheet has no question header and must be skipped.")


def no_header_xlsx(out: Path) -> None:
    name = "Ad-hoc questions from procurement.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Sheet1"
    expected = []
    for _d, _r, question in pick({"Infrastructure", "Encryption"}):
        sheet.append([question, ""])
        expected.append(question)
    write(out / "questionnaires" / name, xlsx_bytes(workbook))
    key(
        out,
        name,
        expected,
        "No header row: extraction asks for a mapping; the eval applies the one a user would pick.",
        mapping={
            "sheets": [{"sheet": "Sheet1", "header_row": None, "question_col": 0, "answer_col": 1}]
        },
    )


def docx_table(out: Path) -> None:
    name = "Vendor Security Questionnaire - Northstar Bank.docx"
    document = Document()
    document.add_heading("Northstar Bank - Third-Party Security Questionnaire", level=0)
    document.add_paragraph("Please complete the table below. Attach evidence where requested.")
    table = document.add_table(rows=1, cols=3)
    for cell, header in zip(table.rows[0].cells, ["No.", "Question", "Response"], strict=True):
        cell.text = header
    expected = []
    for i, (_d, _r, question) in enumerate(
        pick({"Governance", "Identity & Access", "Incident Response"}), start=1
    ):
        cells = table.add_row().cells
        cells[0].text, cells[1].text, cells[2].text = str(i), question, ""
        expected.append(question)
    write(out / "questionnaires" / name, docx_bytes(document))
    key(out, name, expected, "Questions in a 3-column table.")


def docx_paragraphs(out: Path) -> None:
    name = "Vendor Due Diligence Questionnaire.docx"
    document = Document()
    document.add_heading("Vendor Due Diligence Questionnaire", level=0)
    document.add_paragraph(
        "Instructions: answer each question in the space provided. Use N/A if a question does not apply."
    )
    expected = []
    number = 1
    for section, domains in [
        ("Security Program", {"Governance"}),
        ("Operations", {"Logging & Monitoring", "Business Continuity"}),
    ]:
        document.add_heading(section, level=1)
        for _d, _r, question in pick(domains):
            document.add_paragraph(f"{number}. {question}")
            document.add_paragraph("Answer:")
            expected.append(question)
            number += 1
    document.add_heading("Narrative", level=1)
    for text in DESCRIBE:
        document.add_paragraph(f"{number}. {text}")
        document.add_paragraph("Answer:")
        expected.append(text)
        number += 1
    for p in document.paragraphs:
        for run in p.runs:
            run.font.size = Pt(11)
    write(out / "questionnaires" / name, docx_bytes(document))
    key(
        out, name, expected, "Numbered paragraphs with Answer: lines and an instructions paragraph."
    )


def questionnaire_pdf(
    title: str, intro: str, sections: list[tuple[str, list[str]]], header: str
) -> bytes:
    pdf = PdfWriter(header=header)
    pdf.heading(title, 0)
    pdf.text(intro, size=10, gap=12)
    number = 1
    for s_index, (section, questions) in enumerate(sections, start=1):
        pdf.heading(f"Section {s_index}: {section}", 1)
        for q_index, question in enumerate(questions, start=1):
            pdf.text(f"{s_index}.{q_index} {question}", gap=2)
            pdf.text("Response: ______________________________________________", size=9.5, gap=10)
            number += 1
    return pdf.bytes()


def pdf_questionnaire(out: Path) -> tuple[str, bytes, list[str]]:
    name = "Security Assessment Questionnaire - City Health.pdf"
    sections = [
        (
            "Governance and Assurance",
            [q for _d, _r, q in pick({"Governance", "Audit & Assurance"})],
        ),
        ("Data Protection", [q for _d, _r, q in pick({"Encryption", "Data Protection"})]),
        (
            "Operations",
            [
                q
                for _d, _r, q in pick(
                    {"Logging & Monitoring", "Incident Response", "Business Continuity"}
                )
            ],
        ),
        ("Narrative Responses", DESCRIBE),
    ]
    data = questionnaire_pdf(
        "City Health Network - Vendor Security Assessment",
        "Please answer all questions below. Responses are reviewed by the City Health information security office. Do not leave questions blank.",
        sections,
        header="City Health Network - Confidential",
    )
    expected = [q for _s, qs in sections for q in qs]
    write(out / "questionnaires" / name, data)
    key(
        out,
        name,
        expected,
        "Text PDF: numbered questions, sections, response lines, running header/footer.",
    )
    return name, data, expected


def scanned(out: Path) -> None:
    name = "Supplier Security Questionnaire (scanned).pdf"
    sections = [
        ("Access Management", [q for _d, _r, q in pick({"Identity & Access"})]),
        ("Development", [q for _d, _r, q in pick({"Secure Development"})]),
    ]
    text_pdf = pymupdf.open(
        stream=questionnaire_pdf(
            "Supplier Security Questionnaire",
            "Complete and return this form to procurement.",
            sections,
            header="Meridian Health Supply - Procurement",
        ),
        filetype="pdf",
    )
    scan = pymupdf.open()
    for page in text_pdf:
        pixmap = page.get_pixmap(dpi=150)
        image_page = scan.new_page(width=page.rect.width, height=page.rect.height)
        image_page.insert_image(image_page.rect, stream=pixmap.tobytes("jpeg", jpg_quality=70))
    expected = [q for _s, qs in sections for q in qs]
    write(out / "questionnaires" / name, scan.tobytes())
    key(out, name, expected, "Image-only PDF (no text layer): needs OCR.")

    # A single page as photos.
    first = text_pdf[0].get_pixmap(dpi=150)
    page_questions = [q for q in expected if q in (text_pdf[0].get_text() or "").replace("\n", " ")]
    for ext, data in (
        ("png", first.tobytes("png")),
        ("jpg", first.tobytes("jpeg", jpg_quality=80)),
    ):
        image_name = f"Supplier questionnaire page 1 (photo).{ext}"
        write(out / "questionnaires" / image_name, data)
        key(
            out,
            image_name,
            page_questions or expected[:6],
            "Image of page 1: needs OCR. Key = questions fully on page 1.",
        )


def csv_questionnaire(out: Path) -> None:
    name = "Vendor Questions.csv"
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "Question", "Answer", "Comments"])
    expected = []
    for _d, ref, question in pick({"Vendor Management", "Human Resources", "Privacy"}):
        writer.writerow([ref, question, "", ""])
        expected.append(question)
    write(out / "questionnaires" / name, buffer.getvalue())
    key(out, name, expected)


def xml_questionnaire(out: Path) -> None:
    name = "Security Questions Export.xml"
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<questionnaire name="GRC Platform Export">']
    expected = []
    for domain in ("Encryption", "Logging & Monitoring"):
        parts.append(f'  <section name="{escape(domain)}">')
        for _d, ref, question in pick({domain}):
            parts.append(f'    <question id="{escape(ref)}">{escape(question)}</question>')
            expected.append(question)
        parts.append("  </section>")
    parts.append("</questionnaire>")
    write(out / "questionnaires" / name, "\n".join(parts) + "\n")
    key(out, name, expected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    out: Path = parser.parse_args().out
    print(f"Writing corpus to {out}")
    build_evidence(out)
    caiq_xlsx(out)
    sig_xlsx(out)
    hecvat_xlsx(out)
    no_header_xlsx(out)
    docx_table(out)
    docx_paragraphs(out)
    pdf_questionnaire(out)
    scanned(out)
    csv_questionnaire(out)
    xml_questionnaire(out)
    write(out / "README.md", README)


README = f"""# QAutos test corpus

Generated by `apps/api/scripts/make_test_corpus.py`. Everything is about one
fictional vendor, **{VENDOR}**; all companies, people and numbers are invented.

- `evidence/`: documents to upload on the Documents page (SOC 2 excerpt, policies,
  standards, MSA security exhibit, SOW, pen test letter, subprocessor list, past answers).
- `questionnaires/`: questionnaires in every supported format, to import.
- `answer-keys/`: the questions each questionnaire really contains, for measuring
  extraction (`uv run python scripts/eval_extraction.py`).
"""

if __name__ == "__main__":
    main()
