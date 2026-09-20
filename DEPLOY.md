# Production Deploy & Launch Checklist

Phase 14 deliverable — see [plan.txt](plan.txt) §14 (Deployment Blueprint),
§19 (Environment & Secrets), §20 (CI/CD Pipeline). This document is the
launch runbook: deploying the backend to Render, the frontend to Vercel, and
verifying the release.

## 0. One-time prerequisites

- Neon Postgres project provisioned; use the pooled connection string from the
  Neon **Connect** dialog. The backend normalizes its standard `sslmode` and
  `channel_binding` parameters for `asyncpg`.
- Managed Redis (Upstash or Redis Cloud) — Render has no built-in Redis
- Object storage bucket (Cloudflare R2 or S3) for audio/video (plan §14)
- Sentry project (backend + frontend DSNs)
- At least one free-tier LLM API key: Groq, OpenRouter, NVIDIA NIM, or Gemini
  (see [plan_addendum.txt](plan_addendum.txt) §A)
- Custom domains registered (backend `api.example.com`, frontend `app.example.com`)

## 1. Secrets — where they live

| Variable                     | Location             | Notes                                    |
| ---------------------------- | -------------------- | ---------------------------------------- |
| `DATABASE_URL`               | Render (web service) | Neon pooled Postgres asyncpg URL         |
| `JWT_SECRET` / `JWT_REFRESH_SECRET` | Render        | Generate: `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `CORS_ALLOWED_ORIGINS`       | Render (web)         | e.g. `https://app.example.com`           |
| `REDIS_URL`                  | Render (web)         | Shared production rate-limit backend     |
| `SENTRY_DSN`                 | Render + Vercel      | Optional; enables error monitoring       |
| `GROQ_API_KEY` (or others)   | Render               | At least one required                    |
| `VITE_API_URL`               | Vercel               | e.g. `https://api.example.com`           |
| `VITE_SENTRY_DSN`            | Vercel               | Optional                                 |
| `GOOGLE_IDENTITY_PLATFORM_PROJECT_ID` | Render (web) | Google Cloud project ID; optional       |
| `VITE_FIREBASE_*`            | Vercel               | Firebase web app config; optional         |

Never commit secrets to Git (plan §14, §19).

## 2. Backend deploy — Render

Blueprint file: [render.yaml](render.yaml). The free-tier profile creates one
service:

1. **`emotion-detection-api`** — FastAPI web service. Health check: `/ready`.
   On the free plan, migrations run in the start command immediately before
   Uvicorn. The reminder scheduler also runs in this single process because
   Render background workers require a paid plan.

Render free web services sleep after 15 minutes without inbound traffic and
can take about a minute to wake. While asleep, the scheduler cannot deliver
reminders. Upgrade to a paid web service plus worker before treating reminders
as reliable or using this deployment for production workloads.

Steps:

1. Push `render.yaml` to `main`.
2. In Render → **New → Blueprint**, point at the repo and review the free web service.
3. Fill in every `sync: false` env var in the dashboard (secrets from §1).
4. Deploy. Keep the manual approval gate on the production service for the
   first few releases (plan §20).

Add the custom domain `api.example.com` under **Settings → Custom Domains**;
Render provisions TLS automatically.

## 3. Frontend deploy — Vercel

Blueprint file: [frontend/vercel.json](frontend/vercel.json). Configures the
Vite build, SPA fallback rewrite for `react-router-dom`, immutable asset
caching, and hardening headers (`X-Frame-Options`, `Referrer-Policy`,
`Permissions-Policy` limiting camera/mic to same-origin).

Steps:

1. In Vercel → **Add New → Project**, import the repo, set the root
   directory to `frontend/`.
2. Set env vars `VITE_API_URL` and (optionally) `VITE_SENTRY_DSN`.
3. Deploy. Add the custom domain `app.example.com`.

### Google Cloud Identity Platform (optional)

1. Enable Identity Platform in a Google Cloud project and add Google as an
   identity provider.
2. Register the Vercel production domain under **Authorized domains**. Do not
   add preview domains to the production project unless they are intentionally
   trusted.
3. Create a Firebase web app for the same project and copy its `apiKey`,
   `authDomain`, `projectId`, and `appId` into the four `VITE_FIREBASE_*`
   Vercel variables.
4. Set `GOOGLE_IDENTITY_PLATFORM_PROJECT_ID` on the Render web service to the
   same `projectId`, then redeploy both services.

## 4. CI/CD — GitHub Actions

Workflows under `.github/workflows/`:

| Workflow             | Trigger                        | Purpose                                             |
| -------------------- | ------------------------------ | --------------------------------------------------- |
| `backend-ci.yml`     | PR / push to `main`            | pytest on SQLite + alembic upgrade against Postgres |
| `frontend-ci.yml`    | PR / push to `main`            | oxlint + `tsc -b` + `vite build`                    |
| `ai-regression.yml`  | PR / push / nightly cron       | AI safety + LLM router regression suite (plan §20)  |
| `smoke.yml`          | manual `workflow_dispatch`     | Post-deploy `/health` + `/ready` + `/chat/providers`|

Merges to `main` auto-deploy backend (Render) and frontend (Vercel).
After the deploy finishes, trigger **Actions → Post-deploy Smoke → Run
workflow**, paste the base URL, and verify PASS.

## 5. Database — migrations & backups

- Migrations run automatically in the Render web pre-deploy phase (`alembic
  upgrade head`). To roll back: use Render **Rollback** on the previous
  successful deploy, then run `alembic downgrade -1` manually if required.
- Neon backups: Point-in-Time Recovery is on by default. Configure retention
  under Neon → Project → **Settings → Storage** based on plan §18 retention
  requirements.
- Weekly manual verification: restore latest backup to a scratch branch and
  run `alembic current` to confirm restored HEAD matches production.

## 6. Launch checks — run in this order

Before flipping the DNS to production traffic:

- [ ] Confirm the Render deploy log shows a successful `alembic upgrade head`.
      Free web services do not include dashboard shell access.
- [ ] `GET https://api.example.com/health` → `{"status":"ok","env":"production",…}`
- [ ] `GET https://api.example.com/ready` → 200 (DB reachable)
- [ ] `GET https://api.example.com/chat/providers` → non-empty `available` list
- [ ] **Actions → Post-deploy Smoke** run against `https://api.example.com`
      PASSes.
- [ ] Frontend loads at `https://app.example.com`, register + login smoke by hand.
- [ ] Send one chat message end-to-end; confirm response streams.
- [ ] While the API is awake, trigger a reminder for `now + 2 min` and confirm
      the web-service scheduler dispatches it in the service logs.
- [ ] Sentry dashboard receives a synthetic error from both backend and
      frontend (temporarily raise / throw, then revert).
- [ ] CORS: from `https://app.example.com` browser console,
      `fetch('https://api.example.com/health')` succeeds; from an unlisted
      origin it is blocked.
- [ ] Rate limits enforced: hammer `/chat/message` past
      `CHAT_RATE_LIMIT_PER_MINUTE`; confirm 429.
- [ ] Data-deletion path (`DELETE /privacy/account`) works against a throwaway
      account and audit row is written (plan §12, §18).

## 7. Rollback

- **Backend**: Render → service → **Deploys → Rollback** to the previous
  build. If migrations were destructive, run `alembic downgrade` before
  rolling back the container.
- **Frontend**: Vercel → project → **Deployments → Promote** the previous
  build to production.
- **Data**: Neon **Restore** from PITR to a new branch, cut over connection
  string via Render env var, redeploy.

## 8. Ongoing

- Rotate `JWT_SECRET`, `JWT_REFRESH_SECRET`, and LLM keys on a schedule and
  immediately on suspected exposure (plan §19).
- Review Sentry weekly; convert repeating errors into issues.
- Track AI cost per user with the metering hooks from plan §21; adjust
  `LLM_PROVIDER_CHAIN` order when a paid fallback becomes necessary.
- Clinical content re-review every 6–12 months (plan §23).
