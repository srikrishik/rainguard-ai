# Phase 4: Hosted Gemma photo analysis

Phase 4 adds an advisory photo-inspection workflow for existing assets. The
backend keeps the provider key private, validates uploaded image bytes, stores
inspection state in MongoDB, and calls the configured hosted Gemma endpoint
only after a pending inspection record has been created.

## Configuration

Add these variables to the backend environment only:

- `GEMMA_API_KEY`: the provider key. Never expose it to the frontend.
- `GEMMA_API_URL`: the complete configured `generateContent` endpoint.
- `GEMMA_MODEL_ID`: the hosted model identifier.

The current provisional values use Google’s Gemini API endpoint and
`gemma-4-26b-a4b-it`. Availability, quota, and billing must be verified for
the intended Google project before a live request. Automated tests use mocked
HTTP and never call Google.

## API workflow

### `POST /assets/{asset_id}/inspections`

Accepts a multipart field named `file`. JPEG, PNG, and WebP files are
supported, with a maximum size of 5 MiB. The declared content type and image
signature are both checked before the asset is looked up or the provider is
called.

The endpoint:

1. Confirms the asset ID is valid and the asset exists.
2. Stores a `pending` inspection record with safe metadata and a SHA-256
   digest.
3. Sends the image and asset context to the configured Gemma service.
4. Validates the response against `GemmaReport`.
5. Stores either a `completed` report or a `failed` record with a safe error
   code.

Reports always require human review. They are observations and advisory
recommendations, not engineering certifications, hidden-condition findings,
or flood-probability predictions.

### `GET /inspections/{inspection_id}`

Returns the persisted inspection record, including its status, timestamps,
safe upload metadata, report when completed, or an error code when inference
failed. Invalid IDs return `400`; missing records return `404`.

Provider failures do not delete the pending record. Authentication,
quota/rate-limit, timeout, network/provider, rejected-request, and malformed
response failures are categorized without returning provider payloads or
exception details. A database failure while saving the final state returns a
controlled error and is not reported as a successful inspection.

## Frontend workflow

Retrieve an existing asset in the asset-management screen, select a JPEG, PNG,
or WebP photo, and choose **Analyze photo**. The frontend displays the file
name, upload/loading state, structured summary, severity, observations,
recommended actions, and the mandatory human-review warning. Errors are
generic and retryable; no provider credential is sent to the browser.

## Verification

Run the backend tests:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Run compilation and the frontend build:

```powershell
.\backend\.venv\Scripts\python.exe -m compileall -q backend\app backend\tests
Set-Location frontend
npm.cmd run build
```

Before a controlled live test, verify the Google project’s model access,
active quota, billing configuration, and image/request limits. Then use a
non-production test image and inspect only the safe response; do not print or
commit the provider key.

## Phase 5A: rule-based risk baseline

The asset view also exposes a provisional maintenance-priority baseline through
`POST /assets/{asset_id}/risk-assessments`. The result is persisted in the
separate `risk_assessments` collection and can be retrieved with
`GET /assets/{asset_id}/risk-assessments/latest`.

The baseline uses only point-in-time data already stored for the asset:
incidents from the last 30 days and completed inspection reports. Pending or
failed inspections are excluded. High-severity inspection findings and repeated
recent incidents increase the score; moderate findings and one recent incident
provide smaller increases. Missing evidence produces warnings and does not
make an asset low risk; an asset without recent incidents or completed
inspection evidence is held at medium priority.

The starting thresholds are documented in `backend/app/risk_service.py` and
are provisional, explainable product heuristics, not validated engineering
standards. Every response requires human review and explicitly avoids flood
probabilities or safety certification. TabPFN remains deferred until suitable
labelled data and an offline evaluation plan exist.

The Phase 5B feasibility decision is recorded in
`docs/phase-5-tabpfn.md`. No TabPFN dependency or model is currently
integrated.
