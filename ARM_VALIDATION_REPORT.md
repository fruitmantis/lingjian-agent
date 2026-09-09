# ARM compatibility validation

This document contains technical compatibility results only. Host addresses, accounts,
credentials, business inventories, uploaded documents and private operational evidence
are deliberately excluded.

## Runtime

Ubuntu 24.04 ARM64, Node.js 22, Python 3.12 and PostgreSQL 16 were verified.
The existing Next.js / FastAPI / SQLAlchemy architecture and business schema are retained.

- Install only required OS packages, without recommendations or a full OS upgrade.
- Use signed Ubuntu ports repositories; compare small metadata downloads before choosing a mirror.
- Verify the official ARM64 Node archive checksum.
- Reuse the npm lockfile and existing `.npmrc`; install only the required ARM64 GNU SWC binary.
- Use ARM64 Python wheels and the already-tested dependency versions.
- Reuse a local browser for remote checks rather than downloading a browser onto the VM.

## Minimal code adaptations

- Optional `BANFEI_API_PROXY_TARGET` exposes the existing API through `/api` on the frontend origin.
  Set frontend `NEXT_PUBLIC_API_BASE_URL=/api` at build time when using this mode.
- Optional `BANFEI_BUILD_CPUS=1` limits Next build workers on small machines.
- Proxy timeout is 420 seconds, covering existing requests whose client budget reaches 390 seconds.
- The client recognizes `/api` when calculating existing request budgets; direct API behavior is unchanged.
- Capability-development submission IDs reuse the existing cryptographic random-ID fallback for HTTP
  origins that lack `crypto.randomUUID`. No ID contract, idempotency or version behavior changes.
- Unset optional proxy settings preserve the current direct-backend local configuration.

## Verification performed

- ARM native imports: psycopg, bcrypt, uvloop, lxml, Pillow and Next SWC passed.
- Backend targeted pytest: authentication, files, OpenAPI, development engine, model network policy
  and V1.2 agent tests: **60 passed**, using an isolated validation database.
- Frontend ARM typecheck and production build: **PASS**.
- Pure frontend compatibility tests: **3 passed**.
- Browser validation via encrypted SSH transport while simulating public HTTP browser semantics:
  login, first-password change, five API reads and nine page types at two resolutions.
- **18 page/viewport checks passed**, with no horizontal overflow or JavaScript errors.
- Resolutions: 1366×768 and 1920×1080.
- No real model requests were issued during this compatibility verification.
- This is targeted ARM verification, not a claim that the full product E2E suite or real-provider
  generation/business acceptance was completed.

## Boundaries

No business API, permissions, schema or model-selection logic was redesigned.
The original machine's database and services were preserved. Remote data-copy evidence and credentials
remain outside Git. Runtime processes remain available for manual testing.

This result is readiness for ARM manual testing, not production approval.
