# Project Audit — 2026-09-19

This report records the defects fixed during the audit, the enhancements added,
the verification performed, and the remaining production recommendations.

## Verified baseline

- Backend automated test suite passes (242 tests at the time of this audit).
- All Alembic migrations apply to a fresh database and converge on one head:
  `28c3e41f9a02`.
- Frontend lint and production build pass with no warnings.
- `npm audit --omit=dev` and `pip-audit -r backend/requirements.txt` report no
  known vulnerabilities.
- Route-level code splitting and shared server-state querying reduced the initial
  application JavaScript bundle from approximately 539 kB to approximately 255 kB.

## Defects fixed

| Severity | Area | Resolution |
| --- | --- | --- |
| Critical | Reminder dispatch | The unauthenticated manual dispatch endpoint is hidden in production. |
| Critical | Upload/body limits | Request size enforcement now covers chunked requests without `Content-Length`, and audio uploads are read with a hard upper bound. |
| High | Neon connectivity | Standard Neon PostgreSQL URLs are normalized for SQLAlchemy/asyncpg, including TLS query parameters. |
| High | Production configuration | Production now fails closed on insecure database, CORS, and JWT settings; worker-only processes validate only applicable settings. |
| High | Refresh tokens | Rotation is atomic and detects replay/races instead of allowing two valid descendants. |
| High | Logout | Normal logout now revokes the refresh token on the server before clearing browser state. |
| High | Redis rate limiting | The distributed sliding-window operation is atomic and rejected requests no longer extend the denial window. |
| Medium | Idempotency | The chat route is covered, bearer tokens are not stored as keys, and reusing a key with a different body returns `409`. |
| Medium | Database pooling | Chat no longer holds a database connection while waiting for a slow language-model response. |
| Medium | Error disclosure | Database and speech-to-text internals are no longer returned to clients. |
| Medium | Registration | Concurrent duplicate registrations return a controlled `409` response. |
| Medium | Reminders | Partial updates validate the resulting full schedule and return typed validation errors. |
| Medium | Account deletion | Deletion clears shared authentication state immediately instead of leaving stale UI state. |
| Medium | Deployment | Migrations moved to Render's pre-deploy phase and runtime roles now have scoped configuration. |

## Enhancements added

- Optional Google Cloud Identity Platform / Firebase sign-in, exchanged for the
  application's existing access and refresh tokens.
- Persistent external identity linkage without exposing provider subject IDs in
  privacy exports.
- Lazy-loaded frontend routes and auth-provider code.
- Shared query-backed loading, caching, error handling, and refresh behavior for
  dashboard, memory, reminders, privacy, therapist, and wellness screens.
- Separate production and development Python dependency files.
- Repository-wide ignore rules for secrets, local databases, dependencies,
  builds, virtual environments, and test caches.
- Regression coverage for request-size bypasses, idempotency conflicts,
  reminder validation, production-only routing/configuration, Neon URLs, and
  Google identity handling.

## Recommended next enhancements

1. Move refresh credentials from browser storage to `Secure`, `HttpOnly`,
   same-site cookies after the final frontend/API domains are known, then add
   explicit CSRF/origin protection.
2. Move the process-local idempotency cache to Redis before running more than
   one web replica.
3. Use a durable task queue for reminders and other background jobs that must
   survive restarts.
4. Apply the existing encrypted-field helper to sensitive production model
   fields; the helper is currently present but not wired into stored data.
5. Add email verification, password reset, MFA, device/session management, and
   account-linking confirmation flows.
6. Add end-to-end, accessibility, mobile-layout, and real PostgreSQL concurrency
   tests.
7. Connect a real email or push notification provider; reminders are currently
   in-app only.
8. Initialize frontend Sentry when `VITE_SENTRY_DSN` is configured; the variable
   is documented but not yet consumed by the frontend runtime.
9. Tighten the production Content Security Policy's `connect-src` after the
   final domains are assigned.
10. Establish Neon backups/restore drills and production observability alerts.

## Live deployment prerequisites

- This directory is not currently a Git repository and has no remote. Vercel
  and Render need a connected source repository (or an authenticated CLI flow).
- Vercel, Render, Neon, and Google Cloud are open at their sign-in screens and
  require the project owner to authenticate.
- The Render Blueprint now targets one free web service. Render has no free
  background-worker plan, so reminders run in the web process and pause while
  the service is asleep.
- Final service names, region, budget, and any custom domains still need to be
  chosen before production provisioning.
