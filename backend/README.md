# Emotional Wellness Platform — Backend

FastAPI backend with a **provider-agnostic LLM adapter** that supports free tiers
from NVIDIA NIM, OpenRouter, Groq, and Google Gemini, with automatic fallback.

See the main [plan.txt](../plan.txt) §4 (Technology Stack) and Addendum §A for
the multi-provider design.

## Free LLM providers supported

| Provider   | Free tier | Get a key                                | OpenAI-compatible |
| ---------- | --------- | ---------------------------------------- | ----------------- |
| Groq       | Yes       | https://console.groq.com/keys            | Yes               |
| OpenRouter | Yes (`:free` models) | https://openrouter.ai/keys    | Yes               |
| NVIDIA NIM | Yes       | https://build.nvidia.com/                | Yes               |
| Gemini     | Yes       | https://aistudio.google.com/app/apikey   | No (native REST)  |

You only need **one** key to run. Set as many as you like — the router will
fall back down the chain (`LLM_PROVIDER_CHAIN` in `.env`) if a provider fails.

## Quick start (Windows PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and paste at least one API key (e.g. GROQ_API_KEY)
uvicorn app.main:app --reload --port 8000
```

Open:

- Swagger UI: http://localhost:8000/docs
- Health:     http://localhost:8000/health
- Providers:  http://localhost:8000/chat/providers

## Try it

```powershell
$body = @{
  messages = @(
    @{ role = "system"; content = "You are a warm, non-judgmental wellness companion. Never diagnose." }
    @{ role = "user";   content = "I've felt anxious all week. What's a small thing I can try tonight?" }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri http://localhost:8000/chat/message `
  -ContentType application/json -Body $body
```

Force a specific provider with `"provider": "groq"` (or `nvidia`, `openrouter`,
`gemini`) in the body. Streaming: `POST /chat/stream` (Server-Sent Events).

## Architecture

```
app/
├── main.py                      FastAPI entry + CORS + /health
├── core/config.py               pydantic-settings, reads .env
├── api/chat.py                  /chat/message, /chat/stream, /chat/providers
├── schemas/chat.py              Request/response models
└── services/ai/llm/
    ├── base.py                  ChatMessage, LLMResponse, LLMProvider ABC
    ├── _openai_compat.py        Shared OpenAI-style transport (streaming + full)
    ├── router.py                LLMRouter with fallback chain
    └── providers/
        ├── nvidia.py            NVIDIA NIM (OpenAI-compatible)
        ├── openrouter.py        OpenRouter (OpenAI-compatible)
        ├── groq.py              Groq (OpenAI-compatible)
        └── gemini.py            Google Gemini (native REST)
```

Adding a new provider = one file in `providers/` + one line in
`_build_registry()` in `router.py`.
