# Handoff and security contract

## Change package

The immutable canonical manifest binds control/implementation revision, exact document digest, target scope/descendants, assessment and inventory references, baseline/exception context, rollback instructions and the planned ring sequence. Canonical JSON uses sorted keys, compact separators and finite values. SHA-256 identifies the proposal; approval attestations are outside the hash to avoid circularity. This digest is not a digital signature.

Two distinct identities provide SECURITY and ENGINEERING decisions against that digest. Neither the control author nor the package author may approve. Admin does not inherit approval permissions. Material changes require a new assessment and new plan. Every approval, progression, export and accepted mock observation rechecks evidence, expiry and the current baseline.

`POST /api/rollouts/{id}/export?draft=true` yields `DRAFT_UNAPPROVED` without changing delivery state. Approved export requires both votes, no blockers and an active pilot/later stage. It yields `APPROVED_DEMO_HANDOFF`, not deployment permission. The artifact includes source document/reference, assessments, context, approvals, recovery instructions and a proposed PR description. It is a JSON review bundle, not an executable Terraform module.

The future Cloud Engineering integration must map the approved proposal into its native repository schema, validate current scope/baseline, preserve exact reviewed content, authenticate receipts and confirm propagation. It must not interpret a demo package as production approval.

## Mock receipts

`POST /api/rollouts/{id}/mock-receipts` accepts only `provenance=DEMO`, a unique event ID, matching manifest/target, implementation digest, observation time and status. Duplicate identical events are idempotent; duplicate IDs with different data conflict. Target/manifest mismatches and old/future events are retained without advancing state. A changed implementation digest becomes DRIFTED. APPLIED is not VERIFIED.

The endpoint is restricted to the demo Cloud Engineer identity. It is intentionally not a production webhook. Authentication, signing, replay windows and independent post-deployment reads are requirements for a live adapter.

## Authorization matrix

| Role | Read authorized scope | Author/assess | Request exception | Security decisions | Engineering review/mock receipts | Plan/export | Admin fixture tools |
| --- | --- | --- | --- | --- | --- | --- | --- |
| VIEWER | Yes | No | No | No | No | No | No |
| CONTROL_ENGINEER | Yes | Yes | Yes | No | No | Yes | No |
| EXCEPTION_REQUESTER | Yes | No | Yes | No | No | No | No |
| SECURITY_APPROVER | Yes | No | No | Yes | No | Export only | No |
| CLOUD_ENGINEER | Yes | No | No | No | Yes | Yes | No |
| ADMIN | Yes | No | No | No | No | No | Yes |

All capabilities also require scope grants. Auth failures are audited separately without credentials. Runtime database permissions exclude audit mutation, and triggers guard append-only history. The database owner can still defeat these controls; independent audit retention is not implemented.

## Explicit limitations and threat boundaries

- Demo login is unauthenticated identity selection, allowed only in local/test mode. Loopback port binding and fail-fast nonlocal config are essential.
- No user-supplied executable code or general policy interpreter. JSON bodies are limited to 64 KiB and schemas reject extra top-level fields.
- Rendering uses React's escaping, no raw HTML injection. Tokens are absent from logs, audit payloads and artifacts.
- Browser sessions use bearer tokens in session storage; production needs an OIDC session architecture and hardened CSP.
- Native exception application is never inferred from governance approval. Revocation/expiry creates cleanup work; it cannot mutate cloud state.
- Rollback does not reverse application migrations or guarantee immediate availability. Emergency recovery belongs to Cloud Engineering's approved process.
