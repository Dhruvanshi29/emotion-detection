# Project Audit — 2026-09-19

This report records the defects fixed during the audit, the enhancements added,
the verification performed, and the remaining production recommendations.

## Implementation update — 2026-09-21

The code work from the original recommendations is now implemented:

| Original recommendation | Current implementation |
| --- | --- |
| Browser credential safety | Refresh tokens are `Secure`/`HttpOnly` cookies, access tokens are memory-only, refresh rotation remains enabled, and browser refresh/logout/password rotation require double-submit CSRF plus production Origin checks. |
| Shared idempotency | Idempotency responses use Redis when configured, with bounded local fallback for development. |
| Durable background work | Reminder delivery, email/push outboxes, journal reflection, and chat emotion analysis survive restarts in database-backed queues with locking, retries, and deduplication. |
| Encryption at rest | Chat, journal, emotion, memory, reminder, notification, wellness, safety, consent, therapist-report, MFA, push-subscription, and queued-job sensitive content uses AES-256-GCM field encryption. Production refuses to boot without a valid 32-byte key. |
| Account security | Email verification, password recovery, authenticator MFA, explicit Google linking, refresh-session review/revocation, and sign-out-all are available. |
| Browser quality testing | Playwright covers desktop/mobile public flows and WCAG A/AA checks; CI runs Chromium tests. PostgreSQL migrations run against PostgreSQL in backend CI. |
| Notifications | SMTP email and VAPID Web Push are optional durable delivery channels alongside the in-app inbox. |
| Frontend monitoring | Sentry initializes only when `VITE_SENTRY_DSN` is configured and strips request bodies, query strings, cookies, and user email. |
| CSP | `connect-src` is restricted to the API, Render, Sentry, and required Google identity endpoints; operators must replace `api.example.com` with the final API domain. |
| Recovery/operations | A scheduled/manual GitHub backup restore drill validates Alembic and essential tables against an isolated restore database. Metrics, health/readiness, structured logs, backend/frontend Sentry, and a production launch runbook are present. |

Additional completed product work includes the full Saaya visual redesign,
onboarding and adult age gate, quick mood check-ins, journal editing,
conversation deletion, real notification badges, theme application, voice and
face histories, native browser face-presence detection when available, optional
semantic embeddings, persisted safety-checked chat streaming, and verified-admin
therapist curation/report workflows.

## Verified baseline

- The full backend automated test suite passes.
- All Alembic migrations apply to a fresh database and converge on one head:
  `8e1f3b4c6d75`.
- Frontend lint and production build pass with no warnings.
- `npm audit --omit=dev` and `pip-audit -r backend/requirements.txt` report no
  known vulnerabilities.
- Route-level code splitting and shared server-state querying keep the initial
  application JavaScript bundle under 300 kB, including monitoring support.

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

## Remaining operator actions

No application-code item from the original recommendation list remains open.
Production still requires owner-controlled infrastructure and secrets:

1. Provision Neon, Redis, SMTP, VAPID, Sentry, and at least one AI provider.
2. Set the deployment variables documented in `.env.example`, `render.yaml`,
   and `DEPLOY.md`, including a stable `FIELD_ENCRYPTION_KEY` that is backed up
   separately from the database.
3. Replace `api.example.com` in the CSP with the final API hostname.
4. Configure `BACKUP_SOURCE_DATABASE_URL` and an isolated
   `BACKUP_RESTORE_DATABASE_URL` GitHub secret, then run the restore drill once.
5. Create Sentry alert rules and notification recipients in the Sentry account;
   repository code cannot select the project owner's escalation contacts.
6. Populate the therapist directory through a verified account listed in
   `THERAPIST_ADMIN_EMAILS`; production no longer loads fictional seed records.

## Live deployment prerequisites

- The repository has a GitHub remote; Vercel and Render still require the
  project owner to authorize their accounts and select the repository.
- Vercel, Render, Neon, and Google Cloud are open at their sign-in screens and
  require the project owner to authenticate.
- The Render Blueprint now targets one free web service. Render has no free
  background-worker plan, so reminders run in the web process and pause while
  the service is asleep.
- Final service names, region, budget, and any custom domains still need to be
  chosen before production provisioning.
