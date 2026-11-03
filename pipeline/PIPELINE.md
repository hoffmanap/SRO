# Two-phase city pipeline

**Phase 1 — build fast, move on.** For each new city: pull its atlas from
the LC Labs bulk Sanborn dataset, read/extract buildings (by eye or via
`extract_sanborn_api.py`), write a `buildings_raw.json`, then run
`build_city.py` once. It coarse-geocodes (nearest cross-street), writes the
GeoJSON/summary/site, and registers the city in `cities.json` with
`status: "geocode_pending"`. Commit, push, move to the next city. No manual
georeferencing in this loop — that's the whole point of splitting it out.

**Phase 2 — refine in one sweep.** Periodically (not per-city), run
`refine_geocoding.py`. It scans `cities.json` for every `geocode_pending`
city, looks for a hand-prepared `control_points.json` (>=3 independently
geocoded landmarks per sheet-cluster, so one can be held out and used to
cross-check the other two — the discipline `alpine_1933/pipeline/georef.py`
used, and the one San Angelo's rushed single-pair attempt skipped), fits a
rotation+scale transform, and only accepts it if the held-out landmark
predicts within `MAX_RESIDUAL_M` (15m). Cities that pass flip to
`status: "complete"`; cities that fail or have no control points yet are
left pending and listed in the sweep's report so you know where to spend
landmark-picking time next.

**What this requires going forward that wasn't captured before:**
`buildings_raw.json` needs a `"px": [x, y]` field per building (its source
pixel position on its sheet) for refinement to work — add this when writing
or extracting buildings in phase 1, even though phase 1 itself doesn't use
it. Without it, phase 2 has nothing to transform.

**Existing cities:** El Paso and Alpine are already `complete` (they used
the careful per-sheet transform by hand). San Angelo is `geocode_pending`
but was built before this pipeline existed, so it has no `px` coordinates
recorded — refining it will need either re-reading its sheets to capture
pixel positions, or a one-off control-points pass like Alpine's.
