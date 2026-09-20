# Emotional Wellness — Frontend

Vite + React + TypeScript + Tailwind v4 + TanStack Query + React Hook Form + Zod
+ React Router. Talks to the FastAPI backend at `VITE_API_URL` (default
`http://127.0.0.1:8000`) and proxies `/auth`, `/users`, `/chat`, `/health` in
dev.

## Scripts

```bash
npm install
npm run dev       # http://127.0.0.1:5173
npm run build
```

## Pages

- `/`           — landing
- `/register`   — create account
- `/login`      — sign in
- `/chat`       — text chat with the NVIDIA-backed backend (auth required)
- `/profile`    — view / update profile + preferences (auth required)

## Tokens

Access + refresh tokens are stored in `localStorage`. `axios` interceptors
attach the access token to every request and single-flight refresh on 401.
