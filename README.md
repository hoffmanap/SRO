# The Lodging Ledger

A city-by-city record of hotels, boarding houses, tenements, and other
single-room-occupancy (SRO) structures, hand-extracted from historic Sanborn
fire-insurance survey maps — built to compare how common these living
situations once were against today.

Live site: https://hoffmanap.github.io/SRO/

## Structure

```
index.html            landing page — lists every city from cities.json
cities.json            registry of cities (one entry per city/survey-year)

cities/
  <city_slug>/
    site/
      index.html        that city's interactive map (the actual deliverable)
      sanborn/           georeferenced sheet images + manifest.json for the map overlay
    pipeline/
      tile_sheet.py            splits a sheet GeoTIFF into tiles for manual reading
      master_extract.py        geocodes extraction JSON -> merged GeoJSON + city_summary.json
      make_sheet_overlays.py   builds the web-sized, georeferenced sheet overlay images
      extractions/
        sheet_<N>.json          hand-extracted findings per sheet (the raw data)
    <city>_<year>_lodging.geojson   merged building-level data for the city
    city_summary.json               per-city rollup: sheets digitized, counts by building type
```

Adding a new city means adding a new `cities/<slug>/` directory with the same
shape, then appending an entry to `cities.json` pointing at its `site/index.html`
and `city_summary.json`. The root `index.html` picks it up automatically.

## Why `city_summary.json` matters for cross-city comparisons

Raw building counts aren't comparable across cities on their own — they scale
with how many sheets got digitized and how much of downtown each survey
covered. `city_summary.json` carries `sheets_digitized` alongside the counts
specifically so a future cross-city dashboard can normalize by that (or by
downtown acreage / period population, if a city wants a more rigorous
denominator) rather than comparing raw totals.

## Sourcing

Source sheets: 1908 Sanborn Fire Insurance Maps (Library of Congress /
Sanborn Map Company, loc.gov). Coordinates are hand-geocoded from sheet pixel
positions — treat as block-level, not parcel-level. Building type is read
from the printed use label on each plate (Hotel, Boarding, Lodgings,
Tenements, Apartments); each record carries a confidence rating.

Raw sheet GeoTIFFs and full-resolution tile sets are not checked into this
repo (too large for git) — only the hand-extraction JSON, the merged
GeoJSON, and the compressed web overlay images used by the map.
