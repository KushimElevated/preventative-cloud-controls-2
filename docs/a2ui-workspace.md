# Agent-driven control engineering workspace

The conventional console remains the primary application. `/assistant` and the Azure control's **Open engineering assistant** link add a selectable A2UI experience. Nothing requires an LLM, cloud credentials, or an agent service.

## Verified compatibility

The implementation targets **A2UI protocol v0.9.1**, the current production specification verified on 2026-10-08. v1.0 remains a candidate. Protocol versions and npm package versions are distinct.

| Dependency | Exact version | Compatibility |
| --- | --- | --- |
| `@a2ui/react` | `0.12.0` | Maintained React renderer; imports use `/v0_9` |
| `@a2ui/web_core` | `0.12.0` | Its versioned schema accepts `v0.9` and `v0.9.1` |
| `zod` | `3.25.76` | Satisfies renderer/core peer requirement |
| `react` / `react-dom` | `19.3.0` | Renderer declares React 18 or 19 compatibility |

All direct A2UI dependencies are pinned in `package.json`; `package-lock.json` locks transitive dependencies. Tests feed a real server-produced surface through the maintained `MessageProcessor`, render it with `A2uiSurface`, and dispatch an action through the processor. The renderer uses client external stores; the application creates it after mounting rather than server-rendering generated surfaces.

Primary references:
- [Current protocol specification](https://a2ui.org/specification/v0.9.1-a2ui/)
- [Maintained renderer compatibility](https://a2ui.org/reference/renderers/)
- [React renderer source and custom-component API](https://github.com/a2ui-project/a2ui/tree/main/renderers/react)

## Architecture and wire contract

`app/assistant.py` keeps the orchestration small: a planner selects a typed intent, authorized domain services hydrate the result, Pydantic validates it, and REST returns a bounded ordered batch of A2UI messages. Each message has `version: "v0.9.1"`; the batch contains `createSurface` followed by `updateComponents`. This is a JSON application transport envelope, not SSE or an A2A implementation. The envelope also carries the assessment ID, revision and evidence digest needed for backend commands. Catalog ID is `urn:cloud-control:engineering-catalog:1` and never triggers a remote fetch.

`frontend/lib/a2ui-contract.ts` independently validates the complete batch using strict Zod schemas before it reaches the maintained renderer. The processor runs with strict integrity checks. The allowlist contains one bounded root and seven design-system components:

| Component | Authoritative records / interaction |
| --- | --- |
| ControlSummary | Current control intent, revision, scope and severity; conventional detail link |
| ImpactAssessment | Persisted assessment counts and resource rows; local filters and authorized scope selection |
| PolicyDiffViewer | Imported baseline effect versus proposed implementation JSON; semantic comparison, not a fabricated document diff |
| EvidencePanel | Inventory/assessment provenance, readiness blockers; local-only review checkmarks |
| ExceptionReview | Current exception disposition; resource selection and exception-request draft |
| RolloutTimeline | Deterministic next steps and actual package states; conventional rollout links |
| ApprovalGate | Current/stale evidence and backend-derived capabilities; refresh or open trusted handoff form |

No basic catalog, markdown/HTML renderer, agent-defined links/styles, expression functions, dynamic component imports, RPC tools, or executable UI payloads are registered. The complete surface is limited to eight components, exactly seven child references and at most 100 resource rows. Cycles, duplicate IDs, mixed surface IDs, wrong catalogs, additional properties, function-call objects, unsupported versions and oversized payloads fail closed. This intentionally supports a constrained subset of the protocol, not arbitrary third-party A2UI streams.

## End-to-end demonstration

1. Enter as Control engineer and select **Open engineering assistant** on the dashboard, or open the Azure control's contextual workspace.
2. Ask the prefilled public-network-access question. Inspect observed fixture configuration, sample request predictions, missing readiness, current exceptions and the draft rollout sequence.
3. Filter by configuration, resource/application/owner, then narrow the target to the Search pilot resource group. Changing target uses backend scope authorization and an assessment for that scope.
4. Select a noncompliant/unknown resource and prepare an exception draft. This creates only a ten-minute, actor-bound confirmation intent. No exception or exemption exists yet.
5. In the **trusted application form**, supply justification, compensating controls, risk owner, expiry and explicit confirmation. The backend revalidates role, identity, resource scope, revision, evidence freshness and expiry; it then creates a normal `REQUESTED` exception. It cannot approve or apply it.
6. The new exception invalidates the old assessment. Refresh and select **Prepare governed handoff**. A conventional review form opens. Existing readiness blockers, exact-manifest approvals and Cloud Engineering ownership still apply.

An upgraded demo database receives the pilot scope through migration 0003. Its old immutable inventory remains unchanged. Use Demo administrator → Load initial risk fixture to populate the pilot scope in a new snapshot, then reassess. Fresh databases already contain the pilot fixture.

## API and audit

| Route | Behavior |
| --- | --- |
| `GET /api/assistant/catalog` | Authenticated catalog identifier and full server contract schema |
| `POST /api/assistant/surfaces` | `question`, `control_id`, `scope_id`; returns a validated deterministic surface |
| `POST /api/assistant/commands` | Only `refresh_assessment`, `draft_exception`, `prepare_handoff`; requires assessment, expected revision and evidence digest |
| `POST /api/assistant/intents/{id}/confirm` | Trusted human exception-request form; same requester only, ten-minute expiry and single consumption |

Surface generation, completed commands, confirmed requests, rejected commands and rejected payloads enter the existing append-only audit system. Raw questions are not logged; only their digest is stored. Tokens, external evidence bodies and credentials are excluded. Conventional domain mutations retain their own audit events. HTTP authentication/authorization is mandatory; A2UI and disabled buttons are not authorization.

The human confirmation flag represents an explicit gesture in the trusted UI. It does not cryptographically prove that a human called a REST endpoint. No future agent tool should receive the confirmation endpoint, approval APIs or deployment credentials; production assurance requires enterprise authentication and step-up confirmation where appropriate. Identity switching is a local demo feature only.

## Adding components

1. Define a narrow Pydantic data model and discriminated component in `app/assistant.py`. Hydrate every metric/status from authorized domain records. Never accept model-authored status fields as facts.
2. Add the equivalent strict Zod model in `lib/a2ui-contract.ts`. Explicitly decide field and collection bounds. Use text nodes for untrusted text.
3. Register a `createComponentImplementation` in `components/assistant/catalog.tsx`. Reuse the existing visual tokens. Child references must use A2UI's `CommonSchemas.ChildList`/component reference APIs; then constrain the permitted topology in both validators.
4. Add the component to the catalog and both bounded topology validators. Change the catalog identifier for incompatible contracts.
5. If an interaction is needed, allowlist its name/context in `actionSchema` and define a typed backend command. Reuse domain authorization and stale-evidence checks. Sensitive mutation must enter a trusted confirmation workflow, never execute from a generated response.
6. Update the real server surface fixture and add cross-contract, renderer, malicious-payload, authorization, stale-evidence and browser tests. Pin compatible dependency versions after checking upstream support.

## Future AI orchestration

`IntentPlanner` is the optional seam. The deterministic implementation recognizes the Azure Search public-access intent; unsupported questions return an explicit limitation. An AI implementation may classify a question into an allowlisted intent. The hydration layer still owns all metrics, statuses, policy documents and permissions. The planner is not passed a database session, bearer token, cloud client, approval tool or confirmation tool.

Future narrative suggestions must use `AI_SUGGESTION` provenance, retain evidence references and be clearly separate from observed facts and simulation estimates. Existing surfaces label rule-based guidance and state that no AI suggestion was generated. External Wiz findings, inventory descriptions and evidence must remain untrusted data: they cannot expand the catalog or tool allowlist. Add model evaluation, provenance and prompt-injection tests before exposing any optional AI adapter.

## Verification and limits

Run backend `uv run pytest -q`, frontend `npm run test:unit`, `npm run typecheck`, and against the running Compose stack `npm run test:e2e`. Browser tests cover filtering, scope selection, human confirmation, stale-evidence recovery, governed handoff navigation and viewer restrictions. CI retains browser screenshots/traces as artifacts.

The demo is Azure-first, REST-batched and limited to 100 resources per surface. It does not implement general natural-language reasoning, live readiness collection, streaming multi-agent collaboration or arbitrary external catalogs. Checkmarks never change evidence. A baseline Audit/Deny comparison does not establish complete effective-policy semantics. Sample denied requests do not establish an outage or a resource blast-radius prediction.
