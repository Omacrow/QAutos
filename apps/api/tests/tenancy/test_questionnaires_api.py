"""Questionnaire import over HTTP, and tenant isolation for questionnaires."""

import uuid
from collections.abc import Iterator

import pytest
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.exc import DBAPIError

from sqa.auth.clerk import ClerkVerifier
from sqa.core.config import Settings
from sqa.db.session import Database
from sqa.main import create_app
from tests.conftest import MintToken
from tests.samples import make_xlsx
from tests.tenancy.test_api_isolation import _auth, _demo_token

pytestmark = pytest.mark.db

XLSX = "application/octet-stream"


@pytest.fixture
def client(app_settings: Settings, verifier: ClerkVerifier) -> Iterator[TestClient]:
    with TestClient(create_app(app_settings, verifier=verifier, redis=FakeAsyncRedis())) as c:
        yield c


def _org(mint_token: MintToken, role: str = "org:admin") -> dict[str, str]:
    return _auth(mint_token(user_id="u", org_id=f"org_{uuid.uuid4().hex[:8]}", role=role))


def _caiq(marker: str = "") -> bytes:
    return make_xlsx(
        {
            "CAIQ": [
                ["Question ID", "Question", "Answer"],
                ["Identity"],
                ["IAM-01", f"Is MFA required for all staff? {marker}", ""],
                ["IAM-02", "How often are access rights reviewed?", ""],
            ]
        }
    )


def _upload(
    client: TestClient, headers: dict[str, str], data: bytes, name: str = "caiq.xlsx"
) -> dict:  # type: ignore[type-arg]
    response = client.post(
        "/v1/questionnaires", headers=headers, files={"file": (name, data, XLSX)}
    )
    assert response.status_code in (200, 201), response.text
    record: dict = response.json()["questionnaire"]  # type: ignore[type-arg]
    return record


def test_import_spreadsheet(client: TestClient, mint_token: MintToken) -> None:
    headers = _org(mint_token)
    record = _upload(client, headers, _caiq())
    assert (record["status"], record["question_count"], record["kind"]) == ("ready", 2, "xlsx")

    detail = client.get(f"/v1/questionnaires/{record['id']}", headers=headers).json()
    assert detail["mapping"]["source"] == "detected"
    assert detail["mapping"]["sheets"][0]["question_col"] == 1

    page = client.get(f"/v1/questionnaires/{record['id']}/questions", headers=headers).json()
    assert page["total"] == 2
    first = page["items"][0]
    assert (first["ref"], first["section"]) == ("IAM-01", "Identity")
    assert first["locator"]["answer_cell"] == "C3"

    actions = [e["action"] for e in client.get("/v1/audit-events", headers=headers).json()]
    assert {"questionnaire.uploaded", "questionnaire.extracted"} <= set(actions)


def test_mapping_flow_for_sheets_without_header(client: TestClient, mint_token: MintToken) -> None:
    headers = _org(mint_token)
    data = make_xlsx({"Sheet1": [["Do you encrypt backups?", ""], ["Is MFA enforced?", ""]]})
    record = _upload(client, headers, data, "adhoc.xlsx")
    assert record["status"] == "needs_mapping"
    detail = client.get(f"/v1/questionnaires/{record['id']}", headers=headers).json()
    assert detail["preview"]["sheets"][0]["rows"][0][0] == "Do you encrypt backups?"

    mapped = client.put(
        f"/v1/questionnaires/{record['id']}/mapping",
        headers=headers,
        json={
            "sheets": [{"sheet": "Sheet1", "header_row": None, "question_col": 0, "answer_col": 1}]
        },
    )
    assert mapped.status_code == 202
    assert mapped.json()["status"] == "ready"
    assert mapped.json()["question_count"] == 2
    assert mapped.json()["mapping"]["source"] == "user"

    bad = client.put(
        f"/v1/questionnaires/{record['id']}/mapping",
        headers=headers,
        json={"sheets": [{"sheet": "Nope", "header_row": 0, "question_col": 0}]},
    )
    assert bad.status_code == 202
    assert (bad.json()["status"], bad.json()["error_code"]) == ("failed", "bad_mapping")


def test_reviewers_can_fix_questions(client: TestClient, mint_token: MintToken) -> None:
    org = f"org_{uuid.uuid4().hex[:8]}"
    editor = _auth(mint_token(user_id="e", org_id=org, role="org:editor"))
    viewer = _auth(mint_token(user_id="v", org_id=org, role="org:member"))
    record = _upload(client, editor, _caiq())
    question = client.get(f"/v1/questionnaires/{record['id']}/questions", headers=editor).json()[
        "items"
    ][0]
    path = f"/v1/questionnaires/{record['id']}/questions/{question['id']}"
    assert client.patch(path, headers=viewer, json={"excluded": True}).status_code == 403

    updated = client.patch(path, headers=editor, json={"text": "Is MFA enforced for everyone?"})
    assert (updated.json()["text"], updated.json()["edited"]) == (
        "Is MFA enforced for everyone?",
        True,
    )
    excluded = client.patch(path, headers=editor, json={"excluded": True}).json()
    assert excluded["excluded"] is True
    assert client.patch(path, headers=editor, json={"text": "x"}).status_code == 422


def test_viewers_cannot_import(client: TestClient, mint_token: MintToken) -> None:
    viewer = _org(mint_token, role="org:member")
    response = client.post(
        "/v1/questionnaires", headers=viewer, files={"file": ("q.xlsx", _caiq(), XLSX)}
    )
    assert response.status_code == 403


def test_questionnaires_are_isolated(client: TestClient, mint_token: MintToken) -> None:
    a = _org(mint_token)
    b = _org(mint_token)
    data = _caiq("isolation")
    record = _upload(client, a, data)
    question = client.get(f"/v1/questionnaires/{record['id']}/questions", headers=a).json()[
        "items"
    ][0]

    assert client.get("/v1/questionnaires", headers=b).json() == []
    base = f"/v1/questionnaires/{record['id']}"
    for method, path, body in [
        ("GET", base, None),
        ("GET", f"{base}/questions", None),
        (
            "PUT",
            f"{base}/mapping",
            {"sheets": [{"sheet": "CAIQ", "header_row": 0, "question_col": 1}]},
        ),
        ("POST", f"{base}/reextract", None),
        ("PATCH", f"{base}/questions/{question['id']}", {"excluded": True}),
        ("DELETE", base, None),
    ]:
        assert client.request(method, path, headers=b, json=body).status_code == 404, path

    # Same file in another org: a separate questionnaire, not a duplicate.
    copy = client.post("/v1/questionnaires", headers=b, files={"file": ("q.xlsx", data, XLSX)})
    assert copy.status_code == 201
    assert copy.json()["questionnaire"]["id"] != record["id"]


def test_duplicates_and_rejections(client: TestClient, mint_token: MintToken) -> None:
    headers = _org(mint_token)
    data = _caiq("dup")
    first = _upload(client, headers, data)
    again = client.post(
        "/v1/questionnaires", headers=headers, files={"file": ("x.xlsx", data, XLSX)}
    )
    assert (again.status_code, again.json()["duplicate"]) == (200, True)
    assert again.json()["questionnaire"]["id"] == first["id"]

    bad = client.post(
        "/v1/questionnaires", headers=headers, files={"file": ("q.exe", b"MZ..", XLSX)}
    )
    assert bad.status_code == 415
    assert "XLSX, CSV, DOCX, PDF, XML" in bad.json()["detail"]


def test_delete_removes_questions(client: TestClient, mint_token: MintToken) -> None:
    headers = _org(mint_token)
    record = _upload(client, headers, _caiq("delete"))
    assert client.delete(f"/v1/questionnaires/{record['id']}", headers=headers).status_code == 204
    assert client.get(f"/v1/questionnaires/{record['id']}", headers=headers).status_code == 404


def test_demo_cannot_import_by_default(app_settings: Settings, verifier: ClerkVerifier) -> None:
    secret = "s" * 40
    settings = app_settings.model_copy(update={"demo_jwt_secret": SecretStr(secret)})
    with TestClient(create_app(settings, verifier=verifier, redis=FakeAsyncRedis())) as c:
        demo = _auth(_demo_token(secret))
        response = c.post(
            "/v1/questionnaires", headers=demo, files={"file": ("q.xlsx", _caiq(), XLSX)}
        )
        assert response.status_code == 403
        assert c.get("/v1/questionnaires", headers=demo).status_code == 200


async def test_question_cannot_reference_another_tenants_questionnaire(db: Database) -> None:
    from sqa.models import Question, Questionnaire

    org_a = await db.ensure_org(f"qa_{uuid.uuid4().hex[:8]}", "A")
    org_b = await db.ensure_org(f"qb_{uuid.uuid4().hex[:8]}", "B")
    questionnaire_b = uuid.uuid4()
    async with db.tenant(org_b) as s:
        s.add(
            Questionnaire(
                id=questionnaire_b,
                org_id=org_b,
                filename="q.xlsx",
                kind="xlsx",
                content_type="x",
                size_bytes=1,
                sha256=uuid.uuid4().hex,
                storage_key="k",
            )
        )
    with pytest.raises(DBAPIError):
        async with db.tenant(org_a) as s:
            s.add(
                Question(org_id=org_a, questionnaire_id=questionnaire_b, ordinal=0, text="planted")
            )
