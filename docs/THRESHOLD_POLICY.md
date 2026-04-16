# MR-ALS Promotion Threshold Policy

**Constant:** `MIN_ELIGIBLE_OUTCOMES` in `scripts/experience_hygiene.py`  
**Current value:** 15  
**Last updated:** 2026-04-15

## Decision Record

### Why 15 and not 50

15 eligible outcomes is enough signal for the adaptive weight optimizer to
produce statistically meaningful `keyword_weight_adjustments` without
over-fitting to a small sample. The optimizer runs in **bootstrap mode**
below this threshold (using the shadow eval set as a proxy) and switches to
**live-data mode** once the threshold is met.

Raising the threshold to 50 created a bootstrap catch-22:

1. The optimizer cannot improve the classifier until it has real outcome data.
2. Real outcome data never becomes 'mature' because 50 is unreachable in the
   early deployment phase — the system had 20 eligible outcomes and was
   permanently stuck in shadow mode.
3. Shadow mode means the artifact's weight adjustments are never applied to
   live routing decisions, so classification accuracy cannot improve.

### Timeline

| Date | Change | Author |
|---|---|---|
| 2026-04-15 | Introduced `MIN_ELIGIBLE_OUTCOMES`, set to 50 | Hermes agent (commit 804bda1) |
| 2026-04-15 | Lowered to 15; added this policy doc | Manual review of bootstrap deadlock |

### When to raise the threshold

You may raise `MIN_ELIGIBLE_OUTCOMES` if:

- The current `n_eligible_outcomes` (check `plugin_sync.py --report`) already
  **exceeds** the new value before you commit, **and**
- You have a specific statistical justification (e.g., moving from binary to
  per-type weight vectors requires more samples per class).

Do **not** raise the threshold speculatively. The system cannot accumulate data
in shadow mode — raising the bar before the data exists is self-defeating.

### Checking the current count

```bash
cd ~/.openclaw/workspace/skills/maintainer/meta-router
python3 scripts/plugin_sync.py --report 2>&1 | grep eligible
```
