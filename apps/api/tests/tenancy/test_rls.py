"""Tenant isolation at the database layer.

These tests connect as the production app role (non-superuser, no BYPASSRLS)
and prove Postgres itself refuses cross-tenant access, independent of any
WHERE clause in application code.
"""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from sqa.db.session import Database
from sqa.models import AuditEvent, Membership, Organization

pytestmark = pytest.mark.db

# Tables that hold no tenant data and are allowed to skip RLS.
RLS_EXEMPT = {"alembic_version"}


async def _two_orgs(db: Database) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    org_a = await db.ensure_org(f"org_a_{suffix}", "Org A")
    org_b = await db.ensure_org(f"org_b_{suffix}", "Org B")
    for org_id, user in ((org_a, "user_a"), (org_b, "user_b")):
        async with db.tenant(org_id) as s:
            s.add(Membership(org_id=org_id, clerk_user_id=user, role="owner"))
            s.add(AuditEvent(org_id=org_id, action="test", actor_clerk_user_id=user))
    return org_a, org_b


async def test_app_role_cannot_bypass_rls(db: Database) -> None:
    async with db.engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).one()
    assert row == (False, False)


async def test_every_table_has_forced_rls_and_a_policy(db: Database) -> None:
    """Meta-test: fails CI if someone adds a table without tenant isolation."""
    async with db.engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                           EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid),
                           EXISTS (SELECT 1 FROM pg_attribute a
                                   WHERE a.attrelid = c.oid AND a.attname = 'org_id'
                                     AND NOT a.attisdropped)
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
                    """
                )
            )
        ).all()
    assert rows, "no tables found"
    for name, rls, forced, has_policy, has_org_id in rows:
        if name in RLS_EXEMPT:
            continue
        assert rls, f"{name}: RLS not enabled"
        assert forced, f"{name}: RLS not forced"
        assert has_policy, f"{name}: no RLS policy"
        assert has_org_id or name == "organizations", f"{name}: missing org_id"


async def test_tenant_sees_only_its_own_rows(db: Database) -> None:
    org_a, org_b = await _two_orgs(db)
    async with db.tenant(org_a) as s:
        orgs = (await s.scalars(select(Organization.id))).all()
        member_orgs = set((await s.scalars(select(Membership.org_id))).all())
        audit_orgs = set((await s.scalars(select(AuditEvent.org_id))).all())
    assert orgs == [org_a]
    assert member_orgs == {org_a}
    assert audit_orgs == {org_a}
    assert org_b not in member_orgs


async def test_no_org_context_returns_nothing(db: Database) -> None:
    await _two_orgs(db)
    async with db.engine.connect() as conn:
        for table in ("organizations", "memberships", "audit_events"):
            count = (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()
            assert count == 0, f"{table} leaked {count} rows without org context"


async def test_cannot_insert_into_other_tenant(db: Database) -> None:
    org_a, org_b = await _two_orgs(db)
    with pytest.raises(DBAPIError, match="row-level security"):
        async with db.tenant(org_a) as s:
            s.add(Membership(org_id=org_b, clerk_user_id="intruder", role="owner"))


async def test_cannot_update_or_delete_other_tenant(db: Database) -> None:
    org_a, org_b = await _two_orgs(db)
    async with db.tenant(org_a) as s:
        updated = await s.execute(
            text("UPDATE memberships SET role = 'viewer' WHERE org_id = :b"), {"b": org_b}
        )
        deleted = await s.execute(text("DELETE FROM memberships WHERE org_id = :b"), {"b": org_b})
    assert updated.rowcount == 0  # type: ignore[attr-defined]
    assert deleted.rowcount == 0  # type: ignore[attr-defined]
    async with db.tenant(org_b) as s:
        roles = (await s.scalars(select(Membership.role))).all()
    assert roles == ["owner"]


async def test_org_context_does_not_leak_across_pooled_transactions(db: Database) -> None:
    org_a, _ = await _two_orgs(db)
    single = Database(str(db.engine.url.render_as_string(hide_password=False)), pool_size=1)
    try:
        async with single.tenant(org_a) as s:
            assert (await s.scalar(select(func.count()).select_from(Membership))) == 1
        # Same physical connection, new transaction: the setting must be gone.
        async with single.engine.connect() as conn:
            count = (await conn.execute(text("SELECT count(*) FROM memberships"))).scalar_one()
            setting = (
                await conn.execute(text("SELECT current_setting('app.org_id', true)"))
            ).scalar_one()
        assert count == 0
        assert setting in (None, "")
    finally:
        await single.dispose()


async def test_audit_log_is_append_only(db: Database) -> None:
    org_a, _ = await _two_orgs(db)
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with db.tenant(org_a) as s:
            await s.execute(text("UPDATE audit_events SET action = 'tampered'"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with db.tenant(org_a) as s:
            await s.execute(text("DELETE FROM audit_events"))


async def test_app_cannot_create_orgs_directly(db: Database) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        async with db.tenant(uuid.uuid4()) as s:
            await s.execute(
                text("INSERT INTO organizations (clerk_org_id, name) VALUES ('x', 'x')")
            )


async def test_ensure_org_is_idempotent(db: Database) -> None:
    clerk_id = f"org_{uuid.uuid4().hex[:8]}"
    first = await db.ensure_org(clerk_id, "Acme")
    second = await db.ensure_org(clerk_id, "Renamed")
    assert first == second


# --- Documents and chunks ----------------------------------------------------------


async def _doc_with_chunk(db: Database, org_id: uuid.UUID, vector: list[float]) -> uuid.UUID:
    from sqa.models import Document, DocumentChunk

    doc_id = uuid.uuid4()
    async with db.tenant(org_id) as s:
        s.add(
            Document(
                id=doc_id,
                org_id=org_id,
                filename="policy.pdf",
                kind="pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256=uuid.uuid4().hex,
                storage_key=f"orgs/{org_id}/documents/{doc_id}/original.pdf",
                status="ready",
            )
        )
        await s.flush()
        s.add(
            DocumentChunk(
                org_id=org_id,
                document_id=doc_id,
                ordinal=0,
                text=f"Backups are encrypted ({org_id})",
                embedding=vector,
                embedding_model="test",
            )
        )
    return doc_id


def _unit_vector(index: int) -> list[float]:
    from sqa.models import EMBEDDING_DIM

    vector = [0.0] * EMBEDDING_DIM
    vector[index] = 1.0
    return vector


async def test_vector_search_never_returns_other_tenants_chunks(db: Database) -> None:
    """The query has no org filter at all: RLS alone must hide org B's chunks,
    even when org B holds the exact nearest neighbour."""
    org_a, org_b = await _two_orgs(db)
    query = _unit_vector(7)
    await _doc_with_chunk(db, org_a, _unit_vector(8))  # far from the query
    await _doc_with_chunk(db, org_b, query)  # identical to the query

    from sqa.models import DocumentChunk

    async with db.tenant(org_a) as s:
        rows = (
            await s.execute(
                select(DocumentChunk.org_id, DocumentChunk.embedding.cosine_distance(query))
                .order_by(DocumentChunk.embedding.cosine_distance(query))
                .limit(10)
            )
        ).all()
        keyword_hits = (
            await s.scalars(
                select(DocumentChunk.org_id).where(
                    DocumentChunk.search_tsv.op("@@")(func.plainto_tsquery("english", "backups"))
                )
            )
        ).all()
    assert rows, "org A should see its own chunk"
    assert {org for org, _ in rows} == {org_a}
    assert min(distance for _, distance in rows) > 0.5  # the exact match is invisible
    assert set(keyword_hits) == {org_a}


async def test_documents_and_chunks_hidden_across_tenants(db: Database) -> None:
    from sqa.models import Document, DocumentChunk

    org_a, org_b = await _two_orgs(db)
    doc_b = await _doc_with_chunk(db, org_b, _unit_vector(1))
    async with db.tenant(org_a) as s:
        assert await s.get(Document, doc_b) is None
        assert (
            await s.scalar(
                select(func.count())
                .select_from(DocumentChunk)
                .where(DocumentChunk.document_id == doc_b)
            )
        ) == 0
        # Writes against the other tenant's rows silently affect nothing.
        deleted = await s.execute(
            text("DELETE FROM document_chunks WHERE document_id = :d"), {"d": doc_b}
        )
        assert deleted.rowcount == 0  # type: ignore[attr-defined]
    async with db.tenant(org_b) as s:
        assert await s.get(Document, doc_b) is not None


async def test_chunk_cannot_reference_another_tenants_document(db: Database) -> None:
    """Even with org A's context and org_id, a chunk can't hang off org B's document."""
    from sqa.models import DocumentChunk

    org_a, org_b = await _two_orgs(db)
    doc_b = await _doc_with_chunk(db, org_b, _unit_vector(2))
    with pytest.raises(DBAPIError):
        async with db.tenant(org_a) as s:
            s.add(
                DocumentChunk(
                    org_id=org_a,
                    document_id=doc_b,
                    ordinal=5,
                    text="planted",
                    embedding=_unit_vector(3),
                    embedding_model="test",
                )
            )
