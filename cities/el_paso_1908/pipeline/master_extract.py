"""
Accumulate extracted labels across all sheets into one master GeoJSON.
Each sheet's findings are appended as a Python list in extractions/sheet_<N>.py
(a simple data file), which this script then geocodes and merges.
"""
import json, os, glob, importlib.util
import rasterio
from rasterio.warp import transform as warp_transform

TILES_DIR = 'pipeline/tiles'
SHEETS_DIR = 'sheets_1908'
EXTRACTIONS_DIR = 'pipeline/extractions'
os.makedirs(EXTRACTIONS_DIR, exist_ok=True)

def find_sheet_tif(sheet_num):
    matches = glob.glob(f"{SHEETS_DIR}/sheet_{sheet_num:03d}_*.tif")
    return matches[0] if matches else None

def geocode(sheet_num, tile_file, frac_x, frac_y):
    tif = find_sheet_tif(sheet_num)
    idx = json.load(open(f"{TILES_DIR}/sheet_{sheet_num}/tile_index.json"))
    t = next(x for x in idx['tiles'] if x['file'] == tile_file)
    x0, y0, x1, y1 = t['px_bounds']
    px = x0 + frac_x * (x1 - x0)
    py = y0 + frac_y * (y1 - y0)
    ds = rasterio.open(tif)
    mx, my = ds.transform * (px, py)
    lons, lats = warp_transform(ds.crs, 'EPSG:4326', [mx], [my])
    return lons[0], lats[0]

CITY_SLUG = 'el_paso'
CITY_LABEL = 'El Paso, TX'
SURVEY_YEAR = 1908

def merge_all():
    features = []
    for f in sorted(glob.glob(f"{EXTRACTIONS_DIR}/sheet_*.json")):
        data = json.load(open(f))
        for e in data:
            lon, lat = geocode(e['sheet'], e['tile'], e['fx'], e['fy'])
            features.append({
                'type': 'Feature',
                'geometry': {'type': 'Point', 'coordinates': [lon, lat]},
                'properties': {
                    'city': CITY_SLUG, 'city_label': CITY_LABEL,
                    'label': e['label'], 'building_type': e['type'],
                    'note': e.get('note',''), 'year': SURVEY_YEAR, 'sheet': e['sheet'],
                    'source_tile': e['tile'], 'confidence': e.get('confidence','medium')
                }
            })
    geojson = {'type': 'FeatureCollection', 'features': features}
    with open('pipeline/el_paso_1908_lodging.geojson', 'w') as fh:
        json.dump(geojson, fh, indent=1)
    print(f"Merged {len(features)} total buildings from {len(glob.glob(f'{EXTRACTIONS_DIR}/sheet_*.json'))} sheets")

    # per-city summary stats -- the denominator cities.json needs for cross-city
    # prevalence comparisons later (raw counts alone aren't comparable across
    # cities with different numbers of sheets digitized / downtown area covered)
    counts_by_type = {}
    for feat in features:
        t = feat['properties']['building_type']
        counts_by_type[t] = counts_by_type.get(t, 0) + 1
    sheets_covered = sorted(set(int(os.path.basename(f).split('_')[1].split('.')[0])
                                 for f in glob.glob(f"{EXTRACTIONS_DIR}/sheet_*.json")))
    summary = {
        'city': CITY_SLUG,
        'city_label': CITY_LABEL,
        'state': 'TX',
        'survey_year': SURVEY_YEAR,
        'sheets_digitized': len(sheets_covered),
        'total_buildings': len(features),
        'counts_by_type': counts_by_type,
        'geojson': 'el_paso_1908_lodging.geojson'
    }
    with open('pipeline/city_summary.json', 'w') as fh:
        json.dump(summary, fh, indent=1)
    return summary

if __name__ == '__main__':
    merge_all()
