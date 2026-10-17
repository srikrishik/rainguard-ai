# Phase 7: Society dashboard and field workflow

## Scope

The Vite frontend now connects to the real FastAPI records rather than relying
on a single manually entered asset. The dashboard loads `GET /assets`, shows
asset cards with society and location context, and opens the existing asset
detail workflow when a card is selected. Empty, loading, and API-error states
are shown explicitly.

The asset detail view continues to load incidents, persisted photo
inspections, the Phase 5A rule-based risk assessment, inspection missions, and
maintenance tasks. Completed Gemma reports remain advisory and require human
review; pending and failed inspections are not rendered as completed reports.
Mission checklist responses and notes can be saved through the existing mission
PATCH endpoint. Maintenance status, completion evidence, and reinspection
actions use the existing persisted task endpoints.

## Data boundaries

RainGuard does not currently have a weather provider or rainfall forecast
endpoint. The dashboard therefore states that rainfall data is unavailable
instead of fabricating a forecast or flood probability. Risk prioritization
continues to use the documented rule-based baseline. TabPFN remains deferred
until labelled outcomes and a compatible offline evaluation environment exist.

## API integration

- `GET /assets` supplies dashboard asset records.
- `GET /assets/{asset_id}` and asset-scoped history endpoints supply the detail
  view.
- `PATCH` is permitted by CORS for mission and maintenance updates.
- MongoDB remains the source of truth, so asset, inspection, mission, and task
  state survives browser refresh.

## Limitations

The dashboard aggregates all accessible assets and does not yet provide a
society selector or weather integration. Risk lookup currently creates a fresh
baseline assessment through the existing endpoint; this preserves the Phase
5A contract but can create multiple assessment records when an asset is
retrieved repeatedly. Field photos and human findings remain subject to the
existing human-review safeguards.
