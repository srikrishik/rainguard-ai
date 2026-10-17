# Phase 5B: TabPFN feasibility report

**Status: deferred — TabPFN was not integrated.**

This report records the repository and environment state used to decide
whether an experimental TabPFN risk model can be added without inventing
training data or claiming unverified performance.

## Available data

The repository `data/` directory contains no dataset files. The application
currently stores the following MongoDB records:

### Assets

- MongoDB identifier
- `society_id`
- `name`
- optional `location`
- optional `description`
- persistence timestamp

Missing fields include asset type, age, dimensions/capacity, material,
coordinates/elevation, exposure, and maintenance outcomes.

### Incidents

- asset identifier
- occurrence timestamp
- free-text summary

Missing fields include severity, duration, rainfall context, affected area,
resolution, cost, recurrence label, and verified outcome.

### Inspections

- asset identifier
- `pending`, `completed`, or `failed` status
- timestamps
- safe image metadata
- completed Gemma report, when available
- failure code, when applicable

Completed reports contain advisory severity, confidence, observations, and
recommended actions. They are not ground-truth labels or engineering
outcomes. Pending and failed inspections are excluded from the rule baseline.

### Maintenance outcomes

No maintenance-task collection, schema, repository, completion status, repair
outcome, cost, or prevention label exists.

**Conclusion:** no genuine labelled outcome dataset exists. Existing records
can produce exploratory features, but they cannot support supervised TabPFN
training or a defensible evaluation.

## Environment check

The check was run without installing anything:

```powershell
.\backend\.venv\Scripts\python.exe -c "import importlib.util, sys; print(sys.version); print('tabpfn=', bool(importlib.util.find_spec('tabpfn'))); print('torch=', bool(importlib.util.find_spec('torch'))); print('numpy=', bool(importlib.util.find_spec('numpy'))); print('sklearn=', bool(importlib.util.find_spec('sklearn')))"
```

Observed result:

- Python: `3.10.8`
- `tabpfn`: unavailable
- `torch`: unavailable
- `numpy`: unavailable
- `scikit-learn`: unavailable

The dependency manifest also contains no TabPFN, PyTorch, NumPy, or
scikit-learn entry. Installation is therefore intentionally deferred until
the data contract, labels, evaluation split, and deployment resource budget
are approved.

## Decision and fallback

The Phase 5A rule-based baseline remains the only risk method:

- it is the default API behavior;
- its thresholds and evidence are transparent;
- it persists human-review-required assessments;
- it does not produce flood probabilities;
- it remains usable when model dependencies or labelled data are absent.

No TabPFN model was trained, downloaded, evaluated, or exposed through the
API. No accuracy, calibration, or comparison result is claimed.

## Reproducible next steps before integration

1. Define a target such as a manually reviewed maintenance-priority outcome.
2. Collect timestamped, asset-level labelled examples with verified outcomes.
3. Define a time-based evaluation split that prevents future-data leakage.
4. Record feature provenance and distinguish missing from zero values.
5. Approve TabPFN and numerical dependency versions for Python 3.10 and the
   deployment target.
6. Install only in an isolated environment after the preceding checks.
7. Compare TabPFN with the Phase 5A baseline offline using documented metrics.
8. Keep the rule baseline as fallback and label any model output experimental.

Synthetic records may be used for plumbing tests only if explicitly marked
synthetic; they must not be used to claim model accuracy or real-world risk.
