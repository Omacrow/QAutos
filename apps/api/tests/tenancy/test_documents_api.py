"""Documents over HTTP: upload -> ingestion -> chunks, and tenant isolation.

The test app runs ingestion inline (QUEUE_BACKEND=inline), so an upload
returns after its chunks are written.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient
from pydantic import SecretStr

from sqa.auth.clerk import ClerkVerifier
from sqa.core.config import Settings
from sqa.main import create_app
from tests.conftest import MintToken
from tests.samples import make_docx, make_pdf, make_xlsx
from tests.tenancy.test_api_isolation import _auth, _demo_token

pytestmark = pytest.mark.db

PDF_TYPE = "application/pdf"


@pytest.fixture
def client(app_settings: Settings, verifier: ClerkVerifier) -> Iterator[TestClient]:
    app = create_app(app_settings, verifier=verifier, redis=FakeAsyncRedis())
    with TestClient(app) as c:
        yield c


def _org() -> str:
    return f"org_{uuid.uuid4().hex[:8]}"


def _policy_pdf(marker: str = "") -> bytes:
    return make_pdf(
        [
            [
                ("Access Control", 16, True),
                (f"Access is reviewed quarterly. {marker}", 10.5, False),
            ],
            [("Encryption", 16, True), ("Data at rest uses AES-256.", 10.5, False)],
        ]
    )


def _upload(
    client: TestClient, headers: dict[str, str], data: bytes, name: str = "Policy.pdf"
) -> dict[str, object]:
    response = client.post(
        "/v1/documents", headers=headers, files={"file": (name, data, "application/octet-stream")}
    )
    assert response.status_code in (200, 201), response.text
    body: dict[str, object] = response.json()
    return body


def test_upload_pdf_produces_cited_chunks(client: TestClient, mint_token: MintToken) -> None:
    editor = _auth(mint_token(user_id="ed", org_id=_org(), role="org:editor"))
    result = _upload(client, editor, _policy_pdf())
    doc = result["document"]
    assert isinstance(doc, dict)
    assert result["duplicate"] is False
    assert doc["status"] == "ready", doc
    assert doc["page_count"] == 2
    assert doc["kind"] == "pdf"
    assert doc["uploaded_by"] == "ed"

    page = client.get(f"/v1/documents/{doc['id']}/chunks", headers=editor).json()
    assert page["total"] == doc["chunk_count"] == 2
    assert [(c["heading"], c["page_start"]) for c in page["items"]] == [
        ("Access Control", 1),
        ("Encryption", 2),
    ]
    assert "embedding" not in page["items"][0]


def test_docx_and_xlsx_uploads(client: TestClient, mint_token: MintToken) -> None:
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    docx = _upload(
        client, owner, make_docx([("h1", "Backups"), ("p", "Nightly, kept 35 days.")]), "BCP.docx"
    )["document"]
    xlsx = _upload(
        client,
        owner,
        make_xlsx({"CAIQ": [["Question", "Answer"], ["Do you use MFA?", "Yes"]]}),
        "Answers.xlsx",
    )["document"]
    assert isinstance(docx, dict)
    assert isinstance(xlsx, dict)
    assert (docx["status"], docx["parser"]) == ("ready", "python-docx")
    assert (xlsx["status"], xlsx["parser"]) == ("ready", "openpyxl")
    chunk = client.get(f"/v1/documents/{xlsx['id']}/chunks", headers=owner).json()["items"][0]
    assert (chunk["sheet"], chunk["row_start"], chunk["row_end"]) == ("CAIQ", 2, 2)
    assert chunk["text"] == "Question: Do you use MFA? | Answer: Yes"


def test_viewers_cannot_upload_or_delete(client: TestClient, mint_token: MintToken) -> None:
    org = _org()
    owner = _auth(mint_token(user_id="o", org_id=org))
    viewer = _auth(mint_token(user_id="v", org_id=org, role="org:member"))
    response = client.post(
        "/v1/documents", headers=viewer, files={"file": ("a.pdf", _policy_pdf(), PDF_TYPE)}
    )
    assert response.status_code == 403
    doc = _upload(client, owner, _policy_pdf())["document"]
    assert isinstance(doc, dict)
    assert client.delete(f"/v1/documents/{doc['id']}", headers=viewer).status_code == 403
    # Viewers can still read.
    assert client.get(f"/v1/documents/{doc['id']}", headers=viewer).status_code == 200


def test_other_org_cannot_reach_documents(client: TestClient, mint_token: MintToken) -> None:
    a = _auth(mint_token(user_id="alice", org_id=_org()))
    b = _auth(mint_token(user_id="bob", org_id=_org()))
    data = _policy_pdf("alpha-only")
    doc = _upload(client, a, data)["document"]
    assert isinstance(doc, dict)
    doc_id = doc["id"]

    assert client.get("/v1/documents", headers=b).json() == []
    for method, path in [
        ("GET", f"/v1/documents/{doc_id}"),
        ("GET", f"/v1/documents/{doc_id}/chunks"),
        ("POST", f"/v1/documents/{doc_id}/download"),
        ("POST", f"/v1/documents/{doc_id}/reprocess"),
        ("DELETE", f"/v1/documents/{doc_id}"),
    ]:
        assert client.request(method, path, headers=b).status_code == 404, path

    # Org B uploading the identical file gets its own copy, not org A's.
    copy = _upload(client, b, data)
    assert copy["duplicate"] is False
    assert isinstance(copy["document"], dict)
    assert copy["document"]["id"] != doc_id
    assert client.get(f"/v1/documents/{doc_id}", headers=a).status_code == 200


def test_duplicate_upload_returns_existing(client: TestClient, mint_token: MintToken) -> None:
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    data = _policy_pdf("dup")  # generated PDFs differ byte-wise each time
    first = _upload(client, owner, data)
    second = client.post(
        "/v1/documents", headers=owner, files={"file": ("renamed.pdf", data, PDF_TYPE)}
    )
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert isinstance(first["document"], dict)
    assert second.json()["document"]["id"] == first["document"]["id"]


@pytest.mark.parametrize(
    ("name", "data", "status"),
    [
        ("notes.txt", b"plain text", 415),
        ("fake.pdf", b"not really a pdf", 415),
        ("empty.pdf", b"", 400),
    ],
)
def test_bad_uploads_are_rejected(
    client: TestClient, mint_token: MintToken, name: str, data: bytes, status: int
) -> None:
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    response = client.post("/v1/documents", headers=owner, files={"file": (name, data, PDF_TYPE)})
    assert response.status_code == status
    assert client.get("/v1/documents", headers=owner).json() == []


def test_oversized_upload_is_rejected(
    app_settings: Settings, verifier: ClerkVerifier, mint_token: MintToken
) -> None:
    settings = app_settings.model_copy(update={"max_upload_bytes": 1000})
    with TestClient(create_app(settings, verifier=verifier, redis=FakeAsyncRedis())) as c:
        owner = _auth(mint_token(user_id="o", org_id=_org()))
        response = c.post(
            "/v1/documents", headers=owner, files={"file": ("a.pdf", _policy_pdf(), PDF_TYPE)}
        )
        assert response.status_code == 413


def test_scanned_pdf_fails_with_reason(client: TestClient, mint_token: MintToken) -> None:
    import pymupdf

    scan = pymupdf.open()
    scan.new_page().draw_rect(pymupdf.Rect(10, 10, 100, 100), fill=(0, 0, 0))
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    doc = _upload(client, owner, scan.tobytes(), "scan.pdf")["document"]
    assert isinstance(doc, dict)
    assert (doc["status"], doc["error_code"], doc["chunk_count"]) == ("failed", "no_text", 0)


def test_download_link_and_audit(client: TestClient, mint_token: MintToken) -> None:
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    data = _policy_pdf("download")
    doc = _upload(client, owner, data, "Säkerhet policy.pdf")["document"]
    assert isinstance(doc, dict)
    link = client.post(f"/v1/documents/{doc['id']}/download", headers=owner).json()
    assert link["expires_in"] == 300
    # The signed link needs no bearer token; it is the credential.
    file = client.get(link["url"].removeprefix("http://testserver"))
    assert file.status_code == 200
    assert file.content == data
    assert file.headers["content-disposition"].startswith("attachment;")
    tampered = link["url"].removeprefix("http://testserver")[:-3] + "abc"
    assert client.get(tampered).status_code == 403

    actions = [e["action"] for e in client.get("/v1/audit-events", headers=owner).json()]
    assert {"document.uploaded", "document.processed", "document.downloaded"} <= set(actions)


def test_delete_removes_document_chunks_and_file(
    client: TestClient, mint_token: MintToken, app_settings: Settings
) -> None:
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    doc = _upload(client, owner, _policy_pdf("delete-me"))["document"]
    assert isinstance(doc, dict)
    stored = list(Path(app_settings.local_storage_dir).rglob(f"*{doc['id']}*/original.pdf"))
    assert len(stored) == 1

    assert client.delete(f"/v1/documents/{doc['id']}", headers=owner).status_code == 204
    assert client.get(f"/v1/documents/{doc['id']}", headers=owner).status_code == 404
    assert not stored[0].exists()
    actions = [e["action"] for e in client.get("/v1/audit-events", headers=owner).json()]
    assert "document.deleted" in actions


def test_reprocess_rebuilds_chunks(client: TestClient, mint_token: MintToken) -> None:
    owner = _auth(mint_token(user_id="o", org_id=_org()))
    doc = _upload(client, owner, _policy_pdf("again"))["document"]
    assert isinstance(doc, dict)
    again = client.post(f"/v1/documents/{doc['id']}/reprocess", headers=owner)
    assert again.status_code == 202
    assert again.json()["status"] == "ready"
    assert again.json()["chunk_count"] == doc["chunk_count"]
    page = client.get(f"/v1/documents/{doc['id']}/chunks", headers=owner).json()
    assert [c["ordinal"] for c in page["items"]] == list(range(page["total"]))


def test_demo_workspace_is_read_only_by_default(
    app_settings: Settings, verifier: ClerkVerifier
) -> None:
    secret = "s" * 40
    settings = app_settings.model_copy(update={"demo_jwt_secret": SecretStr(secret)})
    with TestClient(create_app(settings, verifier=verifier, redis=FakeAsyncRedis())) as c:
        demo = _auth(_demo_token(secret))
        docs = c.get("/v1/documents", headers=demo).json()
        # Seeded on startup and ingested through the normal pipeline.
        assert {d["kind"] for d in docs} == {"pdf", "docx", "xlsx"}
        assert all(d["status"] == "ready" and d["chunk_count"] > 0 for d in docs)

        response = c.post(
            "/v1/documents", headers=demo, files={"file": ("a.pdf", _policy_pdf(), PDF_TYPE)}
        )
        assert response.status_code == 403
        assert c.delete(f"/v1/documents/{docs[0]['id']}", headers=demo).status_code == 403
        # Reading and downloading still work.
        assert c.post(f"/v1/documents/{docs[0]['id']}/download", headers=demo).status_code == 200
