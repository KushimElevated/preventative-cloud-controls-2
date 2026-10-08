# Cloud Security Control Engineering Platform

A runnable, local-only engineering workspace for turning security intent into reviewed preventive-control changes. Cloud Security owns intent and governance; Cloud Engineering owns deployment execution.

**This is a fixture-driven MVP, not a production security service. No cloud credentials, cloud mutation methods, live GitHub integration, Wiz connection, or production SSO are implemented.** Demo identity switching does not prove real-world separation of duties.

## Run locally

Prerequisites: Docker Engine/Desktop with Docker Compose v2, internet for the initial image/dependency build, and available local ports 3000/8000.

```bash
git clone https://github.com/KushimElevated/preventative-cloud-controls-2.git
cd preventative-cloud-controls-2
# Until the PR is merged:
git checkout codex/cloud-control-mvp
cp .env.example .env
docker compose up --build --wait
```

Open [the console](http://localhost:3000). API health: [localhost:8000/health](http://localhost:8000/health). Generated schema: [localhost:8000/openapi.json](http://localhost:8000/openapi.json).

The first startup creates a PostgreSQL owner role and a distinct runtime role, applies Alembic migrations, and seeds synthetic data. Runtime cannot modify audit history. Web/API ports bind to **127.0.0.1**; PostgreSQL is not published to the host. Do not expose these containers to a shared network. `.env.example` contains disposable local-only passwords, not real credentials; use URL-safe values if changing them.

After images/dependencies are installed, the application and fixtures require no cloud or other external service. Fonts/assets are local. Interactive Swagger CDN assets are deliberately not enabled; the OpenAPI JSON remains available.

### Demo identities

| Identity | Role | Scope |
| --- | --- | --- |
| `engineer` | Control author, assessment, planning and export | Both demo estates |
| `security` | Security and exception reviewer | Both demo estates |
| `cloud` | Engineering reviewer and mock pipeline observations | Both demo estates |
| `requester` | Application exception requester | Both demo estates |
| `viewer` | Read-only | Both demo estates |
| `admin` | Fixture administration and reconciliation; no approval bypass | Both demo estates |
| `dev-requester` | Restricted exception requester | Azure development only |

Opaque, expiring bearer sessions are generated server-side. Role and scope grants are loaded from the database, not client headers. The browser keeps the token in session storage. Changing identity revokes the previous session.

## Five-minute walkthrough

For the new interactive experience, choose **Open engineering assistant** on the dashboard or Azure Control Detail. Ask the prefilled Azure AI Search question, filter the resource evidence, select the production/pilot scope, review readiness and prepare an exception draft or governed handoff. It uses real A2UI rendering with a deterministic backend and requires no AI credentials. [A2UI architecture, security contract and extension guide](docs/a2ui-workspace.md).

1. Enter as **Control engineer**. Open the Azure AI Search control and inspect its initial impact assessment. Configuration, request effects, exceptions, and readiness are separate.
2. Switch to **Demo administrator** → Demo workspace → **Load remediated fixture**. This creates synthetic readiness evidence; it does not remediate anything in Azure.
3. Switch to **Control engineer** → Azure control → Impact assessment → **Run assessment** → **Prepare rollout**. Enter a rollback/recovery runbook.
4. Open Rollouts & handoff. As **Security approver**, record a rationale and approve. Switch to **Cloud engineer** and provide the second approval.
5. As **Control engineer**, advance through observation to pilot. Download the **Approved handoff** JSON bundle.
6. As **Cloud engineer**, record a **mock verified** receipt. The dashboard should show 6 verified compliant Azure control-resource pairs out of 10 assessed applicable pairs across both controls, with the effective Azure exemption reported separately. These are demonstration results only.
7. Record a mock drifted receipt, create a new control revision, or load another inventory snapshot. Old packages must not continue to support verified coverage.
8. Inspect Exceptions and Audit trail. A pending or approved-but-unapplied request is not an effective exemption; expiry is calculated even without reconciliation running.

The AWS example intentionally shows an account with missing/insecure Block Public Access prerequisites. Narrow its assessment to the protected Claims account to exercise a ready scope. The supported SCP protects an established baseline; it does not establish that baseline or provide an audit effect.

## What works

- Selectable A2UI workspace with seven custom renderers, validated surfaces, scoped commands, explicit evidence provenance and expiring human-confirmation drafts.

- Control creation, immutable revisions, draft deletion, and catalog retirement via API.
- Supported AWS SCP and Azure Policy implementations with digest-bound fixture evaluators.
- Versioned inventory, scope hierarchy, imported mock native baselines, and reproducible impact assessments.
- Time-bound exception requests, distinct governance/native states, review, renewal lineage through API, and mock application/removal receipts.
- Exact-manifest approvals with author/requester checks, optimistic concurrency, stale-evidence checks, staged rollouts and pause/cancel commands.
- Deterministic review bundles containing policy artifacts, assessment evidence, exceptions, approvals, scope, and rollback instructions.
- Idempotent mock pipeline receipts, mismatch/staleness rejection, drift visibility, and fresh-evidence coverage calculations.
- Persisted dashboard, control details, implementation, assessment, exception, rollout, revision history, and audit views.
- SQLAlchemy models, Alembic migrations, PostgreSQL runtime role separation, append-only history protection, local demo auth, and tests.

## API examples

The examples use `curl` and `jq`. They never deploy infrastructure.

```bash
API=http://localhost:8000
TOKEN=$(curl -fsS "$API/api/auth/demo" -H 'Content-Type: application/json' \
  -d '{"user_id":"engineer"}' | jq -r .access_token)

curl -fsS "$API/api/controls" -H "Authorization: Bearer $TOKEN"

curl -fsS "$API/api/controls/azure-search/assessments" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scope_id":"az-prod"}'

curl -fsS "$API/api/exceptions?limit=50&offset=0" \
  -H "Authorization: Bearer $TOKEN"

# After creating a rollout and replacing ROLLOUT_ID with its returned ID:
curl -fsS -X POST "$API/api/rollouts/ROLLOUT_ID/export?draft=true" \
  -H "Authorization: Bearer $TOKEN"
```

Use `/api/auth/demo` with `security` or `cloud` to receive a separate reviewer session. Submit approvals to `/api/rollouts/{id}/approvals` with `decision`, `reason`, and the current `expected_version`. A body-supplied role or an `X-Role` header cannot grant permissions. OpenAPI documents all input shapes.

## Development and tests

Python 3.12+, uv 0.12.19, Node 22+, npm. Exact resolved dependencies are in `backend/uv.lock` and `frontend/package-lock.json`.

```bash
cd backend
uv sync --frozen
uv run ruff check app tests
uv run pytest -q

# PostgreSQL integration suite: use a disposable instance with CREATE DATABASE rights.
# Each test creates and drops its own unique test_controls_* database.
TEST_DATABASE_URL=postgresql+psycopg://test_owner:test-only-password@localhost:5432/postgres \
  uv run pytest -q
```

Without `TEST_DATABASE_URL`, tests use separate temporary SQLite databases and the same Alembic migrations. This is useful portable feedback, **not PostgreSQL verification**. CI runs the suite against PostgreSQL 17. Do not point `TEST_DATABASE_URL` at a production instance.

```bash
cd frontend
npm ci
npm run typecheck
npm run build
# With the full Compose application running:
npx playwright install chromium
npm run test:e2e
```

For local processes instead of containers, configure `DATABASE_URL`, run `uv run alembic upgrade head` and `uv run python -m app.cli seed`, then `uv run uvicorn app.main:app --host 127.0.0.1`. Run `npm run dev` in `frontend`; its default API target is `127.0.0.1:8000`. SQLite may be used for an offline preview with a workspace-specific `sqlite:///...` URL; PostgreSQL is the intended Compose runtime.

CI jobs: PostgreSQL backend tests; frontend typecheck/build; complete Compose startup plus a browser workflow and restart health check. No infrastructure deployment workflow is included.

## Persistence and reset

`docker compose stop` preserves data. `docker compose start` restarts existing containers. `docker compose up --build --wait` rebuilds and runs migrations/seed idempotently. Demo fixture tools add snapshots without deleting history.

```bash
docker compose exec api /app/.venv/bin/python -m app.cli reconcile
```

Schedule that idempotent command using the enterprise's existing scheduler later. It records expiry/cleanup work, never cloud changes.

For a **deliberate destructive reset of this demo database only**, first export anything needed, then run `docker compose down --volumes` from this repository and start again. The removed demo database volume cannot be recovered without a backup.

## Repository map

```text
backend/
  app/          domain rules, providers, services, API, models, demo auth and fixtures
  migrations/   relational schema and append-only protections
  tests/        deterministic domain tests and migrated API integration tests
frontend/
  app/          Next.js routing, layout and styles
  components/   connected workspace, pages and forms
  lib/          typed API client and response shapes
  tests/        A2UI renderer/contract tests, server fixture, Playwright workflows
ops/            local PostgreSQL role bootstrap
docs/           architecture, assumptions, feasibility and handoff/security contracts
.github/        verification workflow only
```

## Known limitations

- A2UI supports the deterministic Azure AI Search assessment flow and a bounded custom catalog. Other natural-language intents return an explicit limitation; no LLM integration is enabled.

- Not production-ready. Local identity switching is deliberately insecure outside a loopback-only demo. Nonlocal environments and live deployment configuration fail startup.
- Only two exact documented template evaluators exist. No arbitrary-policy interpretation, full IAM simulation, live reachability analysis, automatic remediation, or deployed cloud verification.
- One implementation per control revision in this MVP; the domain separates intent from implementation but the UI/API does not yet expose many simultaneous implementations for one revision.
- Scope ancestry is evaluated; request predictions remain bounded fixture rules. Imported policy interactions are evidence, not a comprehensive effective-permissions model.
- Native exception representation is demonstrated for Azure only. AWS bucket-level exceptions are explicitly unsupported.
- Rollout stage labels do not broaden target scopes. A new scope requires a new assessment and package. Paused plans require a new reviewed plan to resume.
- Matching mock receipts do not constitute trusted live attestations. Artifact signing and authenticated pipeline callbacks are future work.
- Refreshing the whole-estate fixture invalidates older assessments, conservatively including unrelated scopes. Fine-grained invalidation is a future increment.
- Lists are paginated by API; the local console loads at most 100 items per list. Large-inventory background processing is not implemented.
- Audit protection is append-only through the app and database permissions/triggers, not externally tamper-proof retention.
- No external plugin credentials, enterprise names/people, or genuine cloud resource data are stored in fixtures.

## Next five increments

1. Agree the Cloud Security/Cloud Engineering handoff contract and integrate read-only existing policy/inventory imports for one pilot scope.
2. Add enterprise OIDC, delegated risk-owner authority, scoped identities, session hardening, and independent audit retention.
3. Add PR creation and authenticated/signed pipeline receipts, with pinned native artifact contracts and recovery exercises.
4. Validate native behavior in a separately approved nonproduction cloud environment; add policy-specific request/readiness tests and real observations.
5. Add incremental reconciliation, scoped invalidation, multiple implementations per intent, scalable pagination/jobs, and outcome metrics from trustworthy telemetry.
