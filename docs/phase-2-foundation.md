# Phase 2 foundation

RainGuard AI currently has a minimal FastAPI backend and Vite frontend. This
phase verifies the local browser-to-API connection without adding product
integrations.

## Prerequisites

- Python 3.10 or newer. Python 3.10.8 was selected as the compatibility
  baseline; Python 3.14.2 is also installed locally.
- Node.js 24 or newer and npm 11 or newer.

## Backend setup

From `backend`:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copy `.env.example` to `.env` only if the default frontend origin needs to be
changed. The backend reads:

- `FRONTEND_ORIGIN`: the single browser origin allowed by CORS. It defaults to
  `http://localhost:5173`.

Start the backend from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```

Verify the API:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

The expected response is:

```json
{"status":"ok","service":"rainguard-api"}
```

## Frontend setup

From `frontend`:

```powershell
npm.cmd install
```

Copy `.env.example` to `.env` only if the backend is not running at the
default URL. Vite exposes:

- `VITE_API_BASE_URL`: the browser-safe base URL for the backend. Do not put
  credentials or other backend secrets in `VITE_*` variables.

Start the frontend:

```powershell
npm.cmd run dev
```

Open `http://localhost:5173`. The page calls
`http://localhost:8000/health` by default and displays the genuine response,
or an explicit loading/error state.

## Tests and build

Run backend tests from the repository root:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
```

Build the frontend from `frontend`:

```powershell
npm.cmd run build
```

The frontend build output is written to `frontend/dist`, which is ignored by
Git.

## Scope and limitations

This phase intentionally does not include MongoDB Atlas, hosted Gemma,
TabPFN, Temporal, Sentry, ElevenLabs, Render, authentication, persistence,
or domain-specific demo endpoints.
