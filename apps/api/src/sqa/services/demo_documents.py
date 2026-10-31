"""Sample evidence for the demo org, generated in code (fictional company).

Built on first start when the demo org has no documents, then ingested
through the normal queue, so the demo exercises the real pipeline.
"""

import hashlib
import io
import uuid

import pymupdf
from docx import Document as new_docx
from openpyxl import Workbook
from sqlalchemy import func, select

from sqa.core.config import Settings
from sqa.core.logging import get_logger
from sqa.db.session import Database
from sqa.ingestion.validate import CONTENT_TYPES
from sqa.models import Document, DocumentKind
from sqa.queue import JobQueue
from sqa.storage import ObjectStore, document_key

log = get_logger(__name__)

# (level, heading, paragraphs). Level 1 headings start a new page.
POLICY: list[tuple[int, str, list[str]]] = [
    (
        1,
        "1. Purpose and Scope",
        [
            "This policy defines how Northwind Inc. protects the confidentiality, integrity and "
            "availability of customer data and the systems that process it. It applies to all "
            "employees, contractors and third parties with access to Northwind production systems.",
            "The policy is owned by the Chief Information Security Officer, reviewed at least "
            "annually, and approved by the executive team. Exceptions require written CISO approval "
            "and are tracked in the risk register with an expiry date.",
        ],
    ),
    (1, "2. Access Control", []),
    (
        2,
        "2.1 Authentication",
        [
            "All workforce access to production systems and corporate applications requires single "
            "sign-on through our identity provider with phishing-resistant multi-factor "
            "authentication (FIDO2 security keys or platform passkeys). SMS one-time codes are not "
            "permitted as a second factor.",
            "Service accounts use short-lived credentials issued by the cloud provider's workload "
            "identity. Long-lived static keys are prohibited and detected by automated scanning.",
        ],
    ),
    (
        2,
        "2.2 Authorization and Least Privilege",
        [
            "Access is granted by role, following least privilege. Production access is limited to "
            "the on-call engineering group and is granted just in time for up to four hours, with "
            "the ticket number recorded.",
            "Access reviews are performed quarterly by system owners. Access for leavers is revoked "
            "within 24 hours of termination, and within one hour for involuntary terminations.",
        ],
    ),
    (1, "3. Encryption", []),
    (
        2,
        "3.1 Data at Rest",
        [
            "Customer data is encrypted at rest using AES-256. Database volumes, object storage and "
            "backups use keys managed in the cloud provider's key management service, with automatic "
            "annual rotation. Access to key material is restricted to the platform team and every "
            "use is logged.",
        ],
    ),
    (
        2,
        "3.2 Data in Transit",
        [
            "All external connections use TLS 1.2 or higher with modern cipher suites; TLS 1.0 and "
            "1.1 are disabled. HSTS is enabled on all public domains. Internal service traffic is "
            "encrypted with mutual TLS.",
        ],
    ),
    (
        1,
        "4. Logging and Monitoring",
        [
            "Security-relevant events from production infrastructure, identity provider and "
            "applications are centralized in our SIEM and retained for 13 months. Alerts are triaged "
            "by the security on-call rotation, which is staffed 24x7.",
            "Audit logs are write-once and cannot be modified by the engineers whose actions they "
            "record.",
        ],
    ),
    (
        1,
        "5. Incident Response",
        [
            "Northwind maintains a documented incident response plan that defines severity levels, "
            "roles, and communication paths. The plan is tested through tabletop exercises at least "
            "twice a year.",
            "Customers are notified of a security incident affecting their data without undue delay "
            "and in any case within 72 hours of confirmation, including the nature of the incident, "
            "the data involved and the measures taken.",
        ],
    ),
    (
        1,
        "6. Vendor Management",
        [
            "Vendors that process customer data are assessed before onboarding and annually "
            "thereafter. Assessments review SOC 2 Type II or ISO 27001 reports, data processing "
            "terms and breach notification commitments. Critical vendors are listed on our public "
            "subprocessor page.",
        ],
    ),
    (
        1,
        "7. Secure Development",
        [
            "All code changes require peer review and pass automated tests, static analysis and "
            "dependency vulnerability scanning before merge. Production deployments run only from "
            "the main branch through the CI pipeline.",
            "An independent firm performs a penetration test of the application at least annually. "
            "Critical findings are remediated within 15 days and high findings within 30 days.",
        ],
    ),
    (
        1,
        "8. Data Retention and Deletion",
        [
            "Customer data is retained for the duration of the contract. Upon termination, customer "
            "data is deleted from production systems within 30 days and from backups within 90 days, "
            "and a certificate of deletion is available on request.",
        ],
    ),
]

BCP: list[tuple[int, str, list[str]]] = [
    (1, "Business Continuity and Disaster Recovery Plan", []),
    (
        2,
        "Objectives",
        [
            "This plan keeps Northwind's service available to customers through disruptions to "
            "people, facilities, suppliers or infrastructure. It is reviewed annually by the VP of "
            "Engineering and tested twice a year.",
        ],
    ),
    (
        2,
        "Recovery Objectives",
        [
            "Northwind commits to a recovery time objective (RTO) of 4 hours and a recovery point "
            "objective (RPO) of 15 minutes for the production service.",
        ],
    ),
    (
        2,
        "Infrastructure Resilience",
        [
            "Production runs across three availability zones in a primary region. Databases use "
            "synchronous replication within the region and asynchronous replication to a secondary "
            "region. Infrastructure is defined as code, so the full environment can be rebuilt in "
            "the secondary region.",
        ],
    ),
    (
        2,
        "Backups",
        [
            "Databases are backed up continuously with point-in-time recovery, and full snapshots "
            "are taken daily. Backups are encrypted, stored in a separate account, and retained for "
            "35 days. Restores are tested monthly.",
        ],
    ),
    (
        2,
        "Testing",
        [
            "A full regional failover exercise was last completed in March and met both the RTO and "
            "RPO targets. Findings from each exercise are tracked to closure.",
        ],
    ),
]

CAIQ_ROWS: list[tuple[str, str, str]] = [
    (
        "A&A-01.1",
        "Are audit and assurance policies established and reviewed annually?",
        "Yes. Our compliance program is reviewed annually and audited by an independent firm.",
    ),
    (
        "A&A-02.1",
        "Are independent audits performed at least annually?",
        "Yes. We complete a SOC 2 Type II audit annually; the latest report covers 12 months.",
    ),
    (
        "BCR-08.1",
        "Is data backed up and are restores tested?",
        "Yes. Continuous backups with point-in-time recovery; restores are tested monthly.",
    ),
    (
        "CEK-03.1",
        "Is data encrypted at rest?",
        "Yes. AES-256 with keys managed in the cloud KMS and rotated annually.",
    ),
    (
        "CEK-04.1",
        "Is data encrypted in transit?",
        "Yes. TLS 1.2+ externally and mutual TLS between internal services.",
    ),
    (
        "DSP-16.1",
        "Is customer data deleted at contract end?",
        "Yes. Deleted from production within 30 days and from backups within 90 days.",
    ),
    (
        "IAM-14.1",
        "Is multi-factor authentication required for privileged access?",
        "Yes. Phishing-resistant MFA (FIDO2) is required for all workforce access.",
    ),
    (
        "IAM-08.1",
        "Are user access rights reviewed periodically?",
        "Yes. Quarterly access reviews by system owners.",
    ),
    (
        "LOG-05.1",
        "Are security logs monitored and retained?",
        "Yes. Centralized in our SIEM, monitored 24x7, retained 13 months.",
    ),
    (
        "SEF-08.1",
        "Are customers notified of security incidents?",
        "Yes. Within 72 hours of confirmation of an incident affecting their data.",
    ),
    (
        "STA-09.1",
        "Are third-party service providers assessed?",
        "Yes. Before onboarding and annually, including review of SOC 2 or ISO 27001 reports.",
    ),
    (
        "TVM-07.1",
        "Are penetration tests performed?",
        "Yes. Annual third-party penetration test; criticals fixed within 15 days.",
    ),
    (
        "HRS-04.1",
        "Do employees complete security awareness training?",
        "Yes. At hire and annually, with monthly phishing simulations.",
    ),
]


def build_policy_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 90), "Northwind Information Security Policy", fontsize=22)
    y = 130.0
    for level, heading, paragraphs in POLICY:
        if (level == 1 and y > 140) or y > 680:
            page, y = doc.new_page(), 90.0
        size = 16 if level == 1 else 13
        page.insert_text((72, y), heading, fontsize=size, fontname="hebo")
        y += size + 10
        for paragraph in paragraphs:
            box = pymupdf.Rect(72, y, 540, 760)
            spare = page.insert_textbox(box, paragraph, fontsize=10.5, fontname="helv")
            y += box.height - spare + 10
    # Running header and footer, which ingestion should strip.
    for index in range(doc.page_count):
        doc[index].insert_text((72, 40), "Northwind Inc. - Confidential", fontsize=8)
        doc[index].insert_text((480, 805), f"Page {index + 1} of {doc.page_count}", fontsize=8)
    data: bytes = doc.tobytes()
    doc.close()
    return data


def build_bcp_docx() -> bytes:
    document = new_docx()
    for level, heading, paragraphs in BCP:
        document.add_heading(heading, level=level)
        for paragraph in paragraphs:
            document.add_paragraph(paragraph)
    table = document.add_table(rows=1, cols=3)
    for cell, text in zip(table.rows[0].cells, ("System", "RTO", "RPO"), strict=True):
        cell.text = text
    for row in (("Customer API", "4 hours", "15 minutes"), ("Admin console", "8 hours", "1 hour")):
        cells = table.add_row().cells
        for cell, text in zip(cells, row, strict=True):
            cell.text = text
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def build_caiq_xlsx() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "CAIQ v4"
    sheet.append(["Control ID", "Question", "Answer"])
    for row in CAIQ_ROWS:
        sheet.append(list(row))
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


DEMO_FILES = [
    ("Northwind Information Security Policy.pdf", DocumentKind.PDF, build_policy_pdf),
    ("Northwind Business Continuity Plan.docx", DocumentKind.DOCX, build_bcp_docx),
    ("Northwind CAIQ v4 Responses 2025.xlsx", DocumentKind.XLSX, build_caiq_xlsx),
]


async def seed_demo_documents(
    db: Database, store: ObjectStore, queue: JobQueue, settings: Settings
) -> None:
    org_id = await db.ensure_org(settings.demo_clerk_org_id, settings.demo_org_name)
    async with db.tenant(org_id) as session:
        count = await session.scalar(
            select(func.count()).select_from(Document).where(Document.org_id == org_id)
        )
    if count:
        return
    created = await add_sample_documents(db, store, queue, org_id)
    log.info("demo_documents_seeded", count=len(created))


async def add_sample_documents(
    db: Database, store: ObjectStore, queue: JobQueue, org_id: uuid.UUID
) -> list[uuid.UUID]:
    """Store the sample files in `org_id` and queue their ingestion.

    Also used by the retrieval benchmark, which runs against a throwaway org.
    """
    created: list[uuid.UUID] = []
    for filename, kind, build in DEMO_FILES:
        data = build()
        document_id = uuid.uuid4()
        key = document_key(org_id, document_id, f"original.{kind.value}")
        await store.put(key, data, CONTENT_TYPES[kind])
        async with db.tenant(org_id) as session:
            session.add(
                Document(
                    id=document_id,
                    org_id=org_id,
                    filename=filename,
                    kind=kind.value,
                    content_type=CONTENT_TYPES[kind],
                    size_bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    storage_key=key,
                    uploaded_by="demo:priya",
                )
            )
        created.append(document_id)
    for document_id in created:
        await queue.enqueue_ingest(org_id, document_id)
    return created
