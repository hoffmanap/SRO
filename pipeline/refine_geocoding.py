#!/usr/bin/env python3
"""
Phase 2: backend precise-geocoding sweep.

Run this periodically (not per-city) against every city whose cities.json
status is "geocode_pending". For each one it looks for a hand-prepared
control_points.json in that city's pipeline/ dir; if present and it passes
a cross-validation check, it recomputes every building's position from a
real pixel-to-world transform and flips the city to status="complete". If
absent or it fails validation, the city is left pending and listed in the
report so a human knows where to spend landmark-picking time next.

Why this is a separate step from build_city.py, and why it needs pixel
coordinates (not just Nominatim queries): San Angelo's attempt to retrofit
a transform from BUILDING TEXT alone (no recorded pixel positions, single
landmark pair, no cross-check) produced a scale off by ~1.8x and two
compass-rose readings that disagreed by >100 degrees -- neither was
trustworthy enough to ship. The fix isn't a smarter solver, it's requiring
the inputs that make the solve checkable: for refinement to work on a city,
its extraction step must record each building's SOURCE PIXEL position on
its sheet (pipeline/extract_sanborn_api.py's EXTRACTION_PROMPT already asks
the model for a bounding box per building -- make sure that's persisted to
buildings_raw.json as "px": [x, y] going forward), and control_points.json
must give >=3 independently-geocoded landmarks per sheet cluster so one can
be held out and used to check the other two, the same discipline Alpine's
georef.py used (see that file's docstring).

control_points.json format, one entry per sheet or sheet-cluster sharing a
transform:
  [
    {"sheets": [2, 3], "scale_m_per_px": 0.0696,
     "points": [
       {"label": "County Courthouse", "px": [1704, 1262], "latlon": [31.4619053, -100.4397639]},
       {"label": "First Baptist Church", "px": [900, 2100], "latlon": [31.4631, -100.4421]},
       {"label": "Santa Fe Depot", "px": [2500, 500], "latlon": [31.4650, -100.4380]}
     ]}
  ]
scale_m_per_px: measured directly off that sheet's own printed scale bar
  (not solved for -- Sanborn scale bars are reliable; rotation is the part
  that needs multiple landmarks).

Usage:
  python3 refine_geocoding.py              # sweep all geocode_pending cities
  python3 refine_geocoding.py --city san_angelo_1913   # just report on one
"""
import argparse
import itertools
import json
import math
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_RESIDUAL_M = 15.0  # a held-out landmark must predict within this to accept the transform


def solve_similarity(p1, p2):
    """Solve rotation+scale (a,b) from one pixel-pair -> east/north-meter pair.
    Returns (a, b) where a=scale*cos(theta), b=scale*sin(theta)."""
    (px1, py1), (e1, n1) = p1
    (px2, py2), (e2, n2) = p2
    dx, dy = px2 - px1, py2 - py1
    right, up = dx, -dy
    # [right  up] [a]   [e2-e1]
    # [up  -right] [b] = [n2-n1]
    de, dn = e2 - e1, n2 - n1
    det = right * (-right) - up * up
    if abs(det) < 1e-9:
        return None
    a = (de * (-right) - up * dn) / det
    b = (right * dn - de * up) / det
    return a, b


def latlon_to_en(lat0, lon0, lat, lon):
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
    return ((lon - lon0) * m_per_deg_lon, (lat - lat0) * m_per_deg_lat)


def en_to_latlon(lat0, lon0, e, n):
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
    return (lat0 + n / m_per_deg_lat, lon0 + e / m_per_deg_lon)


def fit_and_validate(points):
    """points: list of {"label","px":[x,y],"latlon":[lat,lon]}, >=3.
    Tries every pair as the solving pair, holds out each remaining point,
    and keeps the (a,b,anchor) whose worst held-out residual is smallest.
    Returns (a, b, anchor_px, anchor_latlon, worst_residual_m) or None."""
    if len(points) < 3:
        return None
    lat0, lon0 = points[0]["latlon"]
    en = [latlon_to_en(lat0, lon0, p["latlon"][0], p["latlon"][1]) for p in points]
    best = None
    for i, j in itertools.permutations(range(len(points)), 2):
        sol = solve_similarity((points[i]["px"], en[i]), (points[j]["px"], en[j]))
        if sol is None:
            continue
        a, b = sol
        worst = 0.0
        for k in range(len(points)):
            if k in (i, j):
                continue
            dx = points[k]["px"][0] - points[i]["px"][0]
            dy = points[k]["px"][1] - points[i]["px"][1]
            right, up = dx, -dy
            pred_e = right * a + up * b
            pred_n = up * a - right * b
            actual_e, actual_n = en[k]
            err = math.hypot(pred_e - actual_e, pred_n - actual_n)
            worst = max(worst, err)
        if best is None or worst < best[-1]:
            best = (a, b, points[i]["px"], points[i]["latlon"], worst)
    return best


def refine_city(slug, registry_entry):
    city_dir = os.path.join(REPO_ROOT, registry_entry["path"])
    cp_path = os.path.join(city_dir, "pipeline", "control_points.json")
    if not os.path.exists(cp_path):
        return ("needs_control_points", None)
    control = json.load(open(cp_path))
    transforms = {}
    for cluster in control:
        fit = fit_and_validate(cluster["points"])
        if fit is None or fit[-1] > MAX_RESIDUAL_M:
            resid = f"{fit[-1]:.1f}m" if fit else "unsolvable"
            return (f"validation_failed (sheets {cluster['sheets']}, held-out error {resid} > {MAX_RESIDUAL_M}m)", None)
        for s in cluster["sheets"]:
            transforms[s] = (fit, cluster["scale_m_per_px"])

    geojson_path = os.path.join(REPO_ROOT, registry_entry["geojson"])
    fc = json.load(open(geojson_path))
    buildings_raw_path = os.path.join(city_dir, "pipeline", "buildings_raw.json")
    if not os.path.exists(buildings_raw_path):
        return ("missing buildings_raw.json with per-building px coords", None)
    buildings_raw = json.load(open(buildings_raw_path))
    px_by_label = {b["label"]: b.get("px") for b in buildings_raw}

    updated = 0
    for f in fc["features"]:
        sheet = f["properties"]["sheet"]
        label = f["properties"]["label"]
        px = px_by_label.get(label)
        if sheet not in transforms or not px:
            continue  # leave this one pending; report will note partial coverage
        (a, b, anchor_px, anchor_latlon, _resid), scale = transforms[sheet]
        # scale_m_per_px folds into (a,b) already from fit_and_validate's own
        # points (which are in meters), so no extra scale multiply needed here.
        dx, dy = px[0] - anchor_px[0], px[1] - anchor_px[1]
        right, up = dx, -dy
        e = right * a + up * b
        n = up * a - right * b
        lat, lon = en_to_latlon(anchor_latlon[0], anchor_latlon[1], e, n)
        f["geometry"]["coordinates"] = [lon, lat]
        f["properties"]["confidence"] = "validated"
        f["properties"]["geocode_method"] = "pixel transform, cross-validated against held-out landmark"
        updated += 1

    if updated == 0:
        return ("control points present but no buildings had matching px coords", None)

    json.dump(fc, open(geojson_path, "w"), indent=1)
    all_validated = updated == len(fc["features"])
    if all_validated:
        summary_path = os.path.join(REPO_ROOT, registry_entry["summary"])
        summary = json.load(open(summary_path))
        summary["geocode_status"] = "complete"
        json.dump(summary, open(summary_path, "w"), indent=1)
    return ("updated", updated if not all_validated else "all")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", help="only process this slug, not the full sweep")
    args = ap.parse_args()

    registry_path = os.path.join(REPO_ROOT, "cities.json")
    registry = json.load(open(registry_path))
    pending = [c for c in registry["cities"] if c["status"] == "geocode_pending"]
    if args.city:
        pending = [c for c in pending if c["slug"] == args.city]

    if not pending:
        print("No geocode_pending cities to refine." if not args.city else f"{args.city} is not geocode_pending.")
        return

    print(f"Sweeping {len(pending)} pending cit{'y' if len(pending)==1 else 'ies'}...\n")
    changed = False
    for c in pending:
        status, detail = refine_city(c["slug"], c)
        if status == "updated":
            print(f"  [OK] {c['city_label']}: {detail} buildings updated"
                  + (" -- status now complete." if detail == "all" else " (partial; still pending)."))
            if detail == "all":
                c["status"] = "complete"
                changed = True
        elif status == "needs_control_points":
            print(f"  [ ] {c['city_label']}: no control_points.json yet -- "
                  f"needs {{sheets, points: [>=3 landmarks with px+latlon]}} at "
                  f"{c['path']}/pipeline/control_points.json")
        else:
            print(f"  [!] {c['city_label']}: {status}")

    if changed:
        json.dump(registry, open(registry_path, "w"), indent=2)
        print("\ncities.json updated -- commit and push.")
    else:
        print("\nNo cities reached full validation this sweep.")


if __name__ == "__main__":
    main()
