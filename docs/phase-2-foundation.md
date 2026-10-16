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
- `MONGODB_URI`: the private MongoDB Atlas connection string. Keep it only in
  the backend environment.
- `DATABASE_NAME`: the MongoDB database name, such as `rainguard`.

The application creates a reusable PyMongo client during FastAPI startup and
closes it during shutdown. It does not expose the connection string. MongoDB
readiness is checked separately from the backward-compatible `/health`
endpoint:

```powershell
Invoke-WebRequest http://localhost:8000/ready
```

`/ready` returns `200` only when MongoDB responds to a safe ping, otherwise it
returns `503` with the generic message `database unavailable`.

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

## Asset-management workflow

The frontend provides the first asset-management workflow:

1. Complete the asset form with the required society ID and asset name.
   Location and description are optional.
2. Submit the form to create the asset through `POST /assets`. The success
   message displays the MongoDB asset ID returned by the API and places that ID
   in the lookup form.
3. Retrieve the asset with `GET /assets/{asset_id}`. The frontend then requests
   `GET /assets/{asset_id}/incidents` and displays the asset record with its
   incident history.

Asset records are stored in MongoDB Atlas, so an asset can be retrieved again
after the browser is reloaded by entering the same returned asset ID. Incident
history is sorted newest first. When no incidents exist, the interface shows
`No incidents recorded for this asset.`; when incidents exist, it displays
their summaries and dates. Loading, success, empty, and safe error states are
shown without exposing database credentials or raw backend exceptions.

To manually verify the workflow:

1. Start the backend and frontend using the commands above.
2. Open `http://localhost:5173` and confirm the system connection reports
   `Connected`.
3. Submit an asset and copy the ID shown in the `Asset created` confirmation.
4. Click `Retrieve` with that ID and confirm the asset record and either the
   populated incident list or the empty-history message.
5. Reload the browser, enter the same asset ID, and retrieve it again to verify
   that the record is persisted in MongoDB Atlas.

`GET /health` is the liveness endpoint and preserves the stable response
`{"status":"ok","service":"rainguard-api"}` when the API process is running.
`GET /ready` is the dependency-readiness endpoint: it returns `200` only when
MongoDB responds to a ping and returns `503` with `database unavailable` when
MongoDB is unavailable.

## Tests and build

Run backend tests from the repository root. They use mocked database
dependencies and do not require MongoDB Atlas credentials:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests
```

Run a syntax/import check:

```powershell
backend\.venv\Scripts\python.exe -m compileall -q backend\app backend\tests
```

Check whitespace errors before committing:

```powershell
git diff --check
```

Build the frontend from `frontend`:

```powershell
npm.cmd run build
```

The frontend build output is written to `frontend/dist`, which is ignored by
Git.

## Scope and limitations

This phase intentionally does not include an asset editing or deletion UI,
public society or incident creation endpoints, hosted Gemma, TabPFN, Temporal,
Sentry, ElevenLabs, Render, authentication, weather data, risk predictions, or
other AI/risk functionality. MongoDB support is limited to the `societies`,
`assets`, and `incidents` collections, with asset creation, asset retrieval,
and incident-history retrieval endpoints.
