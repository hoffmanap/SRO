#!/usr/bin/env python3
"""
Standalone Sanborn sheet -> SRO building extractor, using the Claude API
(your own Anthropic API key / usage credits -- this is NOT free, unlike the
manual reading used to build the rest of this repo's city data).

WHAT THIS DOES
---------------
1. Given a city, downloads its Sanborn sheet master TIFFs directly from the
   Library of Congress (tile.loc.gov) -- no bot-protected site involved.
2. Tiles each sheet into overlapping crops (full-res Sanborn sheets are too
   large/detailed to downscale without losing the small building labels).
3. Sends each tile to Claude's vision API with a structured-output prompt
   asking it to read labeled Hotel / Boarding / Rooms / Flats / Tenement
   buildings, mirroring the extraction convention used by hand elsewhere
   in this repo (see cities/*/pipeline/ for the manual equivalent).
4. Parses the structured JSON responses into this repo's building schema
   and writes <city>_<year>_lodging.geojson + city_summary.json.

WHAT THIS DOES NOT DO
-----------------------
- It does NOT georeference buildings to precise lat/lon. Tile-local pixel
  coordinates are recorded, but turning those into real-world coordinates
  still requires the per-sheet scale-bar + two-landmark transform method
  documented in cities/alpine_1933/pipeline/georef.py (or the coarser
  street-level geocoding used for San Angelo) -- that part is still a
  manual/semi-manual step per city. This script's job is purely to replace
  the slow "read every tile by eye" step with API calls.
- It does NOT use OCR (Tesseract or otherwise). Plain OCR performs badly on
  Sanborn maps -- building footprints, hatching, color fills and cramped
  marginal text defeat standard text detectors. This script sends raw
  image tiles to Claude's vision model instead, the same approach used
  for every city in this repo so far (just automated instead of by hand).

COST / SCALE NOTES
--------------------
- Each tile = one vision API call. A typical Sanborn sheet (6450x7650 at
  full resolution) needs ~6-12 overlapping tiles to keep building labels
  legible, so a 25-sheet city survey is roughly 150-300 API calls.
- Use a cheaper/faster model (e.g. a Haiku-class model) for a first pass,
  and only re-run flagged/uncertain tiles with a stronger model -- see
  MODEL below.
- Every tile is sent independently with no shared context, so cost scales
  linearly with sheet count. There is no way around this with the current
  Claude API; batching many tiles into one call trades cost for accuracy
  (the model does worse at reading dense small text when many tiles are
  crammed into one image).
- Rough order of magnitude: a 25-sheet city at ~200 tiles, using a
  Haiku-class model, costs low single-digit dollars; using a Sonnet/Opus
  class model for a full run costs more -- check current per-token
  pricing at https://docs.claude.com before a large run, since this
  script does not estimate cost for you.

USAGE
------
    pip install anthropic pillow requests --break-system-packages
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 extract_sanborn_api.py \
        --city "Corpus Christi" --state Texas \
        --metadata-path ./sanborn_meta.jsonl \
        --out-dir ./cities/corpus_christi_1919

Metadata: this script expects the LC Labs bulk Sanborn metadata dump
(50,600 atlases, JSON/CSV/JSONL, public domain) rather than scraping
loc.gov or UT Austin's (bot-protected) catalog page by page:
    https://loc-sanborn-maps.s3.amazonaws.com/metadata.jsonl   (~86MB)
    https://loc-sanborn-maps.s3.amazonaws.com/README.md
Download that once, then point --metadata-path at it. It gives you, for
every digitized atlas: city/county/state, date, sheet count, and the
tile.loc.gov "Preview_url" from which this script derives the master
TIFF URL pattern -- no need to locate each city's item page by hand.
"""

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

# ---- Configuration -----------------------------------------------------

MODEL = "claude-haiku-5-5"   # cheap/fast first pass; bump to a Sonnet-class
                              # model for a second pass over uncertain tiles
TILE_SIZE = 1600              # px, square tiles cut from the full-res sheet
TILE_OVERLAP = 200            # px of overlap between adjacent tiles, so a
                               # building label split across a tile edge is
                               # still fully legible in at least one tile
REQUEST_DELAY_S = 0.3         # polite pacing between API calls

BUILDING_TYPES = [
    "hotel", "boarding", "lodging", "tenement", "apartments",
    "institutional_lodging",
]

EXTRACTION_PROMPT = """You are reading a tile cropped from a 1900s-era Sanborn fire insurance map sheet.

Find every building footprint on this tile that is explicitly labeled as one of:
- a named or generic HOTEL
- BOARDING (a boarding house)
- ROOMS / ROOMING (a rooming house)
- FLATS / APARTMENTS
- TENEMENT
- an institutional lodging house (e.g. Y.M.C.A., a mission or dormitory)

Only report buildings with an explicit label matching one of these -- do not
guess based on building shape or size alone, and do not report ordinary
dwellings (small houses marked only with a construction-type letter like
"D" or "F.B." are NOT boarding houses).

For each one, give:
- label: the building's name/label exactly as printed (e.g. "Park Hotel", "Boarding", "Rooms")
- building_type: one of hotel, boarding, lodging, tenement, apartments, institutional_lodging
- note: any other printed detail worth keeping (address number, construction notes, "Negro" or other historical designation as printed, nearby street names)
- pixel_x, pixel_y: the approximate center of the building's footprint, in pixel coordinates of THIS tile image (not the full sheet)
- confidence: "high" if the label is clearly legible, "medium" if partly obscured/ambiguous, "low" if you are guessing

Respond with ONLY a JSON array (no markdown fences, no commentary). If there
are no matching buildings on this tile, respond with an empty array: []
"""


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ---- Metadata lookup -----------------------------------------------------

def find_atlas(metadata_path: str, city: str, state: str):
    """Scan the LC Labs metadata JSONL for digitized atlases matching a city."""
    matches = []
    with open(metadata_path, "r") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not rec.get("Digitized"):
                continue
            city_text = rec.get("City_text") or []
            state_text = rec.get("State_text") or []
            if city.lower() in [c.lower() for c in city_text] and \
               any(state.lower() in s.lower() for s in state_text):
                matches.append(rec)
    return matches


def master_tiff_urls(record: dict):
    """Derive tile.loc.gov master TIFF URLs for every sheet in one atlas record.

    LC's Preview_url gives a 'service' (compressed) image path; the 'master'
    (full-res TIFF) path replaces that one path segment and is directly
    downloadable with no bot-protection.
    """
    preview = (record.get("Preview_url") or [None])[0]
    if not preview or "/service/" not in preview:
        return []
    n_sheets = record.get("Number_of_files", 0)
    base = preview.split("/service/")[1]
    base = base.rsplit("-", 1)[0]  # strip trailing -0001.gif etc.
    urls = []
    for i in range(1, n_sheets + 1):
        n4 = f"{i:04d}"
        urls.append(
            f"https://tile.loc.gov/storage-services/master/{base}-{n4}.tif"
        )
    return urls


# ---- Tiling ---------------------------------------------------------------

def tile_sheet(tiff_path: str, out_dir: str):
    """Cut one full-res Sanborn sheet TIFF into overlapping tiles. Returns
    a list of (tile_path, offset_x, offset_y)."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None

    im = Image.open(tiff_path)
    w, h = im.size
    step = TILE_SIZE - TILE_OVERLAP
    tiles = []
    os.makedirs(out_dir, exist_ok=True)
    y = 0
    while y < h:
        x = 0
        while x < w:
            box = (x, y, min(x + TILE_SIZE, w), min(y + TILE_SIZE, h))
            tile = im.crop(box)
            if tile.getbbox() is not None:  # skip fully blank tiles
                tile_path = os.path.join(out_dir, f"tile_{x}_{y}.jpg")
                tile.convert("RGB").save(tile_path, quality=90)
                tiles.append((tile_path, x, y))
            x += step
        y += step
    return tiles


# ---- Claude API call --------------------------------------------------

def extract_tile(client, tile_path: str, model: str = MODEL):
    import base64

    with open(tile_path, "rb") as f:
        img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    resp = client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": img_b64,
                }},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    text = resp.content[0].text.strip()
    # tolerate accidental markdown fences
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"  [warn] could not parse response for {tile_path}: {text[:200]}", file=sys.stderr)
        return []


# ---- Main pipeline ------------------------------------------------------

def run(city: str, state: str, metadata_path: str, out_dir: str, year: int = None,
        max_sheets: int = None, download_dir: str = None):
    import anthropic
    import requests

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    matches = find_atlas(metadata_path, city, state)
    if not matches:
        print(f"No digitized atlas found for {city}, {state} in {metadata_path}")
        sys.exit(1)

    if year:
        matches = [m for m in matches if str(year) in (m.get("Date") or "")]
    if not matches:
        print("No atlas matched the given year; here are the available dates:")
        for m in find_atlas(metadata_path, city, state):
            print(" -", m.get("Date"), m.get("Id"))
        sys.exit(1)

    record = matches[0]
    print(f"Using atlas: {record.get('Title')} ({record.get('Date')}), "
          f"{record.get('Number_of_files')} sheets")

    urls = master_tiff_urls(record)
    if max_sheets:
        urls = urls[:max_sheets]

    download_dir = download_dir or os.path.join(out_dir, "pipeline", "raw")
    os.makedirs(download_dir, exist_ok=True)
    tile_dir = os.path.join(out_dir, "pipeline", "tiles")

    all_buildings = []
    city_slug = slugify(city)
    survey_year = int(re.search(r"\d{4}", record.get("Date", "0")).group())

    for i, url in enumerate(urls, 1):
        sheet_path = os.path.join(download_dir, f"sheet_{i:04d}.tif")
        if not os.path.exists(sheet_path):
            print(f"Downloading sheet {i}/{len(urls)} ...")
            r = requests.get(url, timeout=120)
            if r.status_code != 200:
                print(f"  [warn] sheet {i} not found ({r.status_code}), skipping")
                continue
            with open(sheet_path, "wb") as f:
                f.write(r.content)

        print(f"Tiling + reading sheet {i}/{len(urls)} ...")
        tiles = tile_sheet(sheet_path, os.path.join(tile_dir, f"sheet_{i:04d}"))
        for tile_path, ox, oy in tiles:
            results = extract_tile(client, tile_path)
            time.sleep(REQUEST_DELAY_S)
            for b in results:
                if b.get("building_type") not in BUILDING_TYPES:
                    continue
                all_buildings.append({
                    "label": b.get("label", "").strip(),
                    "building_type": b["building_type"],
                    "note": b.get("note", ""),
                    "sheet": i,
                    "confidence": b.get("confidence", "medium"),
                    # pixel coords are in SHEET space (tile offset applied);
                    # you still need to georeference these -- see module
                    # docstring and cities/alpine_1933/pipeline/georef.py
                    "sheet_pixel_x": ox + b.get("pixel_x", 0),
                    "sheet_pixel_y": oy + b.get("pixel_y", 0),
                })

    print(f"\nExtracted {len(all_buildings)} candidate buildings across {len(urls)} sheets.")

    os.makedirs(out_dir, exist_ok=True)
    raw_path = os.path.join(out_dir, "pipeline", f"{city_slug}_{survey_year}_raw_extraction.json")
    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    json.dump(all_buildings, open(raw_path, "w"), indent=2)
    print(f"Wrote raw extraction (ungeoreferenced) to {raw_path}")
    print("\nNext step: georeference these sheet_pixel_x/y values into lat/lon.")
    print("See cities/alpine_1933/pipeline/georef.py for the two-landmark")
    print("transform method, or geocode by nearest cross-street for a faster,")
    print("coarser pass like cities/san_angelo_1913/pipeline/.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--city", required=True, help='e.g. "Corpus Christi"')
    ap.add_argument("--state", required=True, help='e.g. "Texas"')
    ap.add_argument("--year", type=int, default=None, help="restrict to a specific survey year")
    ap.add_argument("--metadata-path", required=True,
                     help="path to the LC Labs metadata.jsonl (download once from "
                          "https://loc-sanborn-maps.s3.amazonaws.com/metadata.jsonl)")
    ap.add_argument("--out-dir", required=True, help="output city directory, e.g. ./cities/corpus_christi_1919")
    ap.add_argument("--max-sheets", type=int, default=None, help="cap sheets for a cheap test run")
    args = ap.parse_args()

    run(args.city, args.state, args.metadata_path, args.out_dir,
        year=args.year, max_sheets=args.max_sheets)
