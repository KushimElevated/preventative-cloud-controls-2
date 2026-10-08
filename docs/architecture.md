# Architecture and design decisions

The MVP is a modular monolith: Next.js UI → FastAPI application services → PostgreSQL. Domain evaluation has no ORM/network dependency. Delivery creates review artifacts and records mock receipts; there is no cloud deployment path.

Security intent is versioned separately from implementation documents. A control has an owning scope for authorization; an assessment can target that scope or a descendant, never a broader scope. The fixture registry currently exposes one implementation per revision. Scope expansion is a new assessed/reviewed package.

`app/domain.py` contains capability-aware AWS/Azure adapters and deterministic evaluators. Exact document matching prevents arbitrary edits from reusing an evaluator. Results distinguish configuration, exception disposition, request prediction and readiness. Unknown evidence blocks operational readiness.

`app/services.py` owns transactions, authorization decisions, gates and state transitions. SQLAlchemy version columns detect stale writes; expected revision/version inputs provide useful client conflicts. Immutable snapshots and assessments have explicit monotonic ordinals so timestamp ties do not select arbitrary evidence. Concurrent ordinal allocation collides safely with a unique constraint and returns 409; retry after reloading. A future high-volume ingestion service should use database-generated sequences.

`app/models.py` holds relational entities. JSON is limited to versioned intent, native documents and evidence payloads; identities, scopes, revisions, approvals and state remain relational. Migrations freeze the initial schema. A distinct database role serves the application in Compose; migrations run as the owner. Audit/history triggers also guard writes at the database boundary.

The API issues random opaque demo tokens and stores hashes/expiry. Grants are server-side. Session switching exists only to demonstrate roles locally; it is not enterprise authentication. All production/nonlocal modes fail closed. Next.js proxies same-origin `/api` requests, avoiding permissive CORS. No cookie authentication is used. Assets/fonts are local. The local demo CSP permits inline scripts/styles needed by Next; production should adopt nonces when real auth is introduced.

Bounded synchronous assessment keeps this understandable for a small team. No task queue, generic policy compiler, AI dependency or new deployment infrastructure is justified by the current fixture volume. An idempotent reconciliation CLI is the seam for a future scheduler.

Configuration coverage requires current evidence and a matching fresh mock observation. Exemptions remain in the applicability denominator and outside protected counts. Resource pairs are deduplicated by `(control_id, resource_id)`. Empty denominators yield null/N/A; unavailable runtime outcomes stay null, not zero.

The dashboard deliberately avoids attacks-prevented or disruption probability claims. Even a matching deployment digest cannot prove application availability or prevent every attack path.
