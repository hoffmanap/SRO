"""
Alpine's source sheets (Library of Congress, Sanborn Map Co., Feb 1933) are
plain scans -- unlike El Paso's, they don't ship with an embedded geotransform.
This script captures the manual control-point method used to place Alpine's
hand-extracted buildings on the map:

  1. One identifiable, still-standing landmark per sheet is geocoded (Hotel
     Holland, First Baptist Church, Sul Ross State University's Administration
     Building, St. James Episcopal Mission) and its pixel position measured on
     that sheet's full-resolution TIFF.
  2. The sheet's own printed scale bar ("100 ft. to one inch") gives feet-per-
     pixel directly -- no external scale assumption needed.
  3. The sheet's compass rose shows true north is rotated ~11 degrees clockwise
     from the sheet's "up" direction (Alpine's grid follows the Southern
     Pacific line, not true north).
  4. Every other building on that sheet is placed via a single similarity
     transform (rotate 11 deg, scale by the measured ft/px, translate from the
     landmark's known lat/lon) -- rather than cell-by-cell georeferencing.

This is coarser than El Paso's per-sheet GeoTIFF alignment: expect block-level
accuracy, not parcel-level. counts_by_type and sheets_digitized in
city_summary.json still carry the digitization-coverage caveat described in
the repo root README.
"""
import math

ROTATION_DEG = 11.0          # true north, clockwise from sheet "up"
SCALE_M_PER_PX = 0.099921    # measured off the printed scale bar on sheet 1

def offset_latlon(anchor_latlon, anchor_px, target_px,
                   rotation_deg=ROTATION_DEG, scale=SCALE_M_PER_PX):
    lat0, lon0 = anchor_latlon
    theta = math.radians(rotation_deg)
    dx = target_px[0] - anchor_px[0]
    dy = target_px[1] - anchor_px[1]
    right_img, up_img = dx, -dy
    true_east = right_img * math.cos(theta) + up_img * math.sin(theta)
    true_north = up_img * math.cos(theta) - right_img * math.sin(theta)
    east_m, north_m = true_east * scale, true_north * scale
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
    return (lat0 + north_m / m_per_deg_lat, lon0 + east_m / m_per_deg_lon)

# Per-sheet anchors: (pixel xy on that sheet's full-res TIFF, real-world lat/lon)
ANCHORS = {
    2: {"landmark": "Hotel Holland",                 "px": (3300, 5600), "latlon": (30.3574016, -103.6628597)},
    3: {"landmark": "First Baptist Church of Alpine", "px": (1670, 2570), "latlon": (30.3594246, -103.6611778)},
    4: {"landmark": "Sul Ross State Univ. Admin Bldg","px": (1600, 700),  "latlon": (30.3640746, -103.6489700)},
    5: {"landmark": "St. James Episcopal Mission",    "px": (2650, 5280), "latlon": (30.3612632, -103.6640704)},
}
