#!/usr/bin/env python3
"""
Phase 1: fast city build-out.

Takes a hand-written (or vision-extracted) buildings_raw.json for one city
and turns it into a live, registered site in one command -- coarse geocode,
GeoJSON, summary, rendered site from the shared template, cities.json entry.
Every building comes out flagged confidence="pending_precise_geocode" and
the city is registered with status="geocode_pending": that's the point of
splitting this into two phases, not an oversight to fix per-city later.

buildings_raw.json format (list of dicts), one entry per identified building:
  {"label": "Hotel Holland", "type": "hotel", "sheet": 2,
   "note": "...what the sheet says...", "query": "Oak St & 5th St"}
`type` must be one of TYPES in site_template.py (hotel/boarding/lodging/
tenement/apartments/institutional_lodging).

Usage:
  python3 build_city.py \\
    --slug waco_1922 --city waco --city-label "Waco, TX" --state TX \\
    --state-full Texas --year 1922 --survey-date "May 1922" \\
    --sheets 18 --scale-label "50 FT./IN." \\
    --buildings-raw ./waco_1922_buildings_raw.json \\
    --bbox 31.52 31.58 -97.16 -97.10 \\
    --anchor 31.5493 -97.1467 \\
    --center 31.5493 -97.1467 --zoom 14 \\
    --about-sub "..." --about-text "..." --source-text "..."

This does NOT run the vision-extraction step (pipeline/extract_sanborn_api.py)
or sheet tiling -- those still need the city's own atlas pulled from the LC
Labs dataset and either hand-reading or the extraction script, same as
before. This script picks up once you have a buildings_raw.json, and handles
everything after that mechanically so it's no longer hand-work.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from geocode_coarse import geocode_buildings
from site_template import render_site

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", required=True, help="e.g. waco_1922")
    ap.add_argument("--city", required=True, help="e.g. waco")
    ap.add_argument("--city-label", required=True, help="e.g. 'Waco, TX'")
    ap.add_argument("--state", required=True, help="2-letter, e.g. TX")
    ap.add_argument("--state-full", required=True, help="e.g. Texas")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--survey-date", required=True, help="e.g. 'May 1922'")
    ap.add_argument("--sheets", type=int, required=True, help="sheets digitized")
    ap.add_argument("--scale-label", default="50 FT./IN.")
    ap.add_argument("--buildings-raw", required=True, help="path to buildings_raw.json")
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("S", "N", "W", "E"))
    ap.add_argument("--anchor", nargs=2, type=float, required=True, metavar=("LAT", "LON"))
    ap.add_argument("--center", nargs=2, type=float, required=True, metavar=("LAT", "LON"))
    ap.add_argument("--zoom", type=int, default=14)
    ap.add_argument("--about-sub", required=True)
    ap.add_argument("--about-text", required=True)
    ap.add_argument("--source-text", required=True)
    args = ap.parse_args()

    city_dir = os.path.join(REPO_ROOT, "cities", args.slug)
    site_dir = os.path.join(city_dir, "site")
    os.makedirs(site_dir, exist_ok=True)

    buildings_raw = json.load(open(args.buildings_raw))
    print(f"[1/5] geocoding {len(buildings_raw)} buildings (coarse, phase 1)...")
    buildings = geocode_buildings(buildings_raw, args.city_label, args.state,
                                   tuple(args.bbox), tuple(args.anchor))

    print("[2/5] writing GeoJSON...")
    features = []
    for b in buildings:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [b["lon"], b["lat"]]},
            "properties": {
                "city": args.city, "city_label": args.city_label,
                "label": b["label"], "building_type": b["type"],
                "note": b["note"], "year": args.year, "sheet": b["sheet"],
                "source_tile": b.get("source_tile", "n/a"),
                "confidence": b["confidence"], "geocode_method": b["geocode_method"],
            },
        })
    geojson_path = os.path.join(city_dir, f"{args.slug}_lodging.geojson")
    json.dump({"type": "FeatureCollection", "features": features}, open(geojson_path, "w"), indent=1)

    print("[3/5] writing city_summary.json...")
    counts = {}
    for b in buildings:
        counts[b["type"]] = counts.get(b["type"], 0) + 1
    summary = {
        "sheets_digitized": args.sheets,
        "total_buildings": len(buildings),
        "counts_by_type": counts,
        "geocode_status": "pending_precise_geocode",
    }
    json.dump(summary, open(os.path.join(city_dir, "city_summary.json"), "w"), indent=1)

    print("[4/5] rendering site from shared template...")
    has_sheets = os.path.exists(os.path.join(site_dir, "sanborn", "manifest.json"))
    html = render_site(
        city_label=args.city_label.split(",")[0], state_full=args.state_full,
        survey_date=args.survey_date, sheets=args.sheets, scale_label=args.scale_label,
        about_sub=args.about_sub, about_text=args.about_text, source_text=args.source_text,
        center_lat=args.center[0], center_lon=args.center[1], zoom=args.zoom,
        geojson_file=f"{args.slug}_lodging.geojson", n_buildings=len(buildings),
        geocode_status="pending", has_sheets=has_sheets, year=args.year,
    )
    open(os.path.join(site_dir, "index.html"), "w").write(html)

    print("[5/5] registering in cities.json...")
    registry_path = os.path.join(REPO_ROOT, "cities.json")
    registry = json.load(open(registry_path))
    registry["cities"] = [c for c in registry["cities"] if c["slug"] != args.slug]
    registry["cities"].append({
        "slug": args.slug, "city": args.city, "city_label": args.city_label,
        "state": args.state, "survey_year": args.year, "status": "geocode_pending",
        "path": f"cities/{args.slug}",
        "site": f"cities/{args.slug}/site/index.html",
        "summary": f"cities/{args.slug}/city_summary.json",
        "geojson": f"cities/{args.slug}/{args.slug}_lodging.geojson",
    })
    json.dump(registry, open(registry_path, "w"), indent=2)

    print(f"\nDone: {args.city_label} built with {len(buildings)} buildings, "
          f"status=geocode_pending. Commit cities/{args.slug}/, cities.json, "
          f"and push -- then move to the next city. Precise geocoding happens "
          f"later, in refine_geocoding.py's sweep across all pending cities.")


if __name__ == "__main__":
    main()
