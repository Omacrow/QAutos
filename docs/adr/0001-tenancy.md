# ADR 0001: Tenant isolation

**Status:** accepted (Phase 1a)

## Decision

Tenant isolation is enforced in two independent layers.

1. **Postgres Row-Level Security.** Every table has RLS *enabled and forced*,
   with a policy matching `org_id` (or `id` on `organizations`) to
   `sqa_current_org()`. That function reads `app.org_id`, which the API sets with
   `set_config(..., true)` at the start of each transaction. The setting is
   transaction-local, so pooled connections can't carry it into another request.
   If it isn't set, queries return zero rows.
2. **Application filters.** Queries also filter on `org_id` explicitly.

The API connects as `sqa_app`, which has no superuser and no BYPASSRLS. Migrations
run as the owner role. The app can't insert organizations directly. It goes through
`sqa_ensure_org()`, a narrow SECURITY DEFINER function that maps a Clerk org id
from a *verified* token to our internal id.

The org and role always come from the Clerk token, never from the URL or request body.

## Evidence

`tests/tenancy/` covers cross-org reads, writes, updates and deletes, the empty
result when no org is set, pooled connections leaking context, the append-only
audit log, and a meta-test that fails if any table lacks forced RLS, a policy or
`org_id`. We verified the tests by weakening a policy to `USING (true)`: 5 tests
failed, and the API-level tests still passed because of layer 2.

Phase 1b's `chunks` table (vectors) gets the same policy, and every vector query
runs inside a tenant session.
