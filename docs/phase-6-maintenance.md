# Phase 6: inspection-to-maintenance workflow

Phase 6 adds a persistent, human-reviewed workflow for moving from an asset
inspection mission to maintenance work. It does not automatically convert a
Gemma report or risk assessment into a task.

## Workflow

1. `POST /assets/{asset_id}/inspection-missions` creates a deterministic
   six-item checklist.
2. `GET /inspection-missions/{mission_id}` retrieves the mission.
3. `POST /inspection-missions/{mission_id}/findings` records a human finding.
4. `POST /inspection-missions/{mission_id}/findings/{finding_id}/approve`
   explicitly approves that finding.
5. `POST /maintenance-tasks` creates a task only for an approved finding.
6. `GET /maintenance-tasks/{task_id}`, asset task listing, and dashboard task
   listing expose persisted work.
7. `PATCH /maintenance-tasks/{task_id}` supports
   `pending -> in_progress -> completed`, plus completion notes and evidence
   references.
8. `POST /maintenance-tasks/{task_id}/reinspection` records that the issue
   still needs verification.

The frontend shows the mission checklist, finding form, approval action, task
list, status controls, and reloaded task history within the existing asset
view. It remains compatible with photo inspections and Phase 5A risk output.

## Persistence

MongoDB collections:

- `inspection_missions`: asset-scoped mission checklist, notes, findings, and
  links to inspection IDs.
- `maintenance_tasks`: approved work items, lifecycle state, completion
  notes, evidence references, and reinspection state.

Indexes:

- Missions: `(asset_id ASC, created_at DESC)`.
- Tasks: `(asset_id ASC, updated_at DESC)`.
- Tasks: unique `(mission_id ASC, finding_id ASC)` to prevent duplicate work
  for the same approved finding.

The repository also checks for an existing mission/finding pair before insert,
so repeated browser submissions return the existing task rather than creating
another document. A database unique index remains the concurrency safeguard.

## Evidence and safeguards

Evidence is represented as validated text references only. Image bytes are
not copied into task documents, and local filesystem paths are not treated as
public URLs. Existing photo upload validation remains unchanged.

Gemma reports and Phase 5A risk assessments remain advisory. A human must
create and explicitly approve a mission finding before a maintenance task can
be created. Completing work does not assert that the underlying issue is
resolved; reinspection is separately recorded.

## Limitations

- There is no authentication or role/permission system for this demonstration.
- Completion evidence references are not file uploads or externally hosted
  URLs.
- Checklist responses are stored with the mission, but the current UI focuses
  on recording findings and does not add a separate evidence-storage service.
- Temporal is intentionally not part of this phase.

## Verification

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests -q
.\backend\.venv\Scripts\python.exe -m compileall -q backend\app backend\tests
node --check frontend\src\main.js
Set-Location frontend
npm.cmd run build
git diff --check
```
