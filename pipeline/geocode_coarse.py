"""
Phase-1 (fast build-out) geocoder: nearest-cross-street via Nominatim.

This is deliberately coarse -- block-level-or-worse -- so a city can go from
"sheets downloaded" to "live on the map" in one sitting. It is NOT the final
geocode: every building it places gets confidence="pending_precise_geocode"
so refine_geocoding.py (the phase-2 backend sweep) knows to revisit it later.
Do not hand-tune this script to be more "precise" -- that temptation is what
burns the time this two-phase split is meant to save. If a building needs to
be placed exactly, that's phase 2's job, with real landmark pairs.

Usage (library, called from build_city.py):
    from geocode_coarse import geocode_buildings
    geocode_buildings(buildings_raw, city_label, state_abbr, bbox)

buildings_raw: list of dicts with at least {label, type, sheet, note, query}
  -- `query` is a short geocodable string, usually the nearest street or
  cross-street pulled off the sheet (e.g. "Chadbourne St" or
  "4th St & Oakes St").
bbox: (south, north, west, east) -- hard sanity filter; any Nominatim hit
  outside this box is rejected (Nominatim will happily return a match in a
  different state for an ambiguous street name).
"""
import json
import random
import time
import urllib.parse
import urllib.request

NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "lodging-ledger-research-project (contact: hoffman.alexp@gmail.com)"


def _nominatim_query(q: str):
    url = NOMINATIM + "?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 3})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return []


def _in_bbox(lat, lon, bbox):
    s, n, w, e = bbox
    return s <= lat <= n and w <= lon <= e


def _hash_jitter(seed_label, anchor, spread_m=120):
    """Deterministic small offset from an anchor point, for buildings whose
    geocode fails outright -- keeps them visibly near downtown rather than
    dropping them (which would silently undercount the city) or stacking
    them exactly on the anchor (which looks like a data error)."""
    rnd = random.Random(seed_label)
    m_per_deg = 111320.0
    dlat = (rnd.random() - 0.5) * 2 * spread_m / m_per_deg
    dlon = (rnd.random() - 0.5) * 2 * spread_m / (m_per_deg * 0.85)
    return (anchor[0] + dlat, anchor[1] + dlon)


def geocode_buildings(buildings_raw, city_label, state_abbr, bbox, anchor_point,
                       rate_limit_s=1.1):
    """Returns a new list of dicts with lat/lon + confidence/geocode_method set.
    anchor_point: (lat, lon) fallback center (e.g. the county courthouse) used
    for the jitter fallback when a query can't be geocoded or lands outside bbox.
    """
    out = []
    for b in buildings_raw:
        q = f"{b['query']}, {city_label}, {state_abbr}"
        hits = _nominatim_query(q)
        time.sleep(rate_limit_s)  # Nominatim usage policy: max 1 req/sec
        picked = None
        for h in hits:
            lat, lon = float(h["lat"]), float(h["lon"])
            if _in_bbox(lat, lon, bbox):
                picked = (lat, lon)
                break
        if picked is None:
            # retry with a bare street name if the full query failed
            plain = b["query"].split("&")[0].strip()
            hits2 = _nominatim_query(f"{plain}, {city_label}, {state_abbr}")
            time.sleep(rate_limit_s)
            for h in hits2:
                lat, lon = float(h["lat"]), float(h["lon"])
                if _in_bbox(lat, lon, bbox):
                    picked = (lat, lon)
                    break
        if picked is None:
            picked = _hash_jitter(b["label"], anchor_point)
        else:
            # small jitter so buildings sharing one geocoded point don't overlap
            picked = _hash_jitter(b["label"] + "_fine", picked, spread_m=25)

        out.append({
            **b,
            "lat": picked[0],
            "lon": picked[1],
            "confidence": "pending_precise_geocode",
            "geocode_method": "approximate (nearest cross-street) -- "
                               "pixel-level georeferencing not yet done for this city",
        })
    return out
