# Implementation checkpoint

Implemented the local-only modular monolith, supported provider evaluators, persisted Azure/AWS demo, approvals/handoff/receipt workflow, connected Next.js console, migrations, Docker Compose and automated checks.

Foundation commit: `24fe43041044727c540ad3190c87407e0efb3844` on `codex/cloud-control-mvp`. GitHub Actions verified PostgreSQL integration tests, the production frontend build and Compose startup. The initial browser workflow found an identity-switch failure; final browser verification remains in progress.

The A2UI extension is implemented with protocol v0.9.1 and React/core 0.12.0. **59 backend tests and Ruff pass locally**; TypeScript passed before adding renderer tests. Backend tests use migrated SQLite locally. Renderer tests, final TypeScript and browser tests are under verification. Local production build remains blocked by the environment's `uv_resident_set_memory` error; no local production-build or browser success is claimed.

Next: finish renderer/browser verification and publish the A2UI extension. All infrastructure deployment remains disabled; only demo artifacts and mock receipts are supported.
