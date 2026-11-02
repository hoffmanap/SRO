"""
Alpine's source sheets (Library of Congress, Sanborn Map Co., Feb 1933) are
plain scans -- unlike El Paso's, they don't ship with an embedded geotransform.
This script captures the control-point method used to place Alpine's
hand-extracted buildings and sheet images on the map.

Method (revised -- see note below on the first version's bugs):
  1. One identifiable, still-standing landmark per sheet is geocoded via
     Nominatim and its pixel position measured on that sheet's full-resolution
     master TIFF (downloaded from tile.loc.gov).
  2. A SECOND identifiable landmark on the same sheet (or, where unavailable,
     on a neighboring sheet of the same town grid) is geocoded and measured
     the same way. The two correspondences are solved as a 2x2 linear system
     for a single similarity transform (rotation + scale, no shear) relating
     pixel space to real-world east/north meters -- this is what ROTATION_DEG
     and the per-scale (a,b) coefficients below encode.
  3. That transform is validated by predicting a third known landmark's
     position from the anchor and checking it against its real geocoded
     location; both sheets checked this way came out within ~5m.
  4. Every other building (and the sheet image's own corner points, for the
     Leaflet.ImageOverlay.Rotated overlay) is placed via this single
     town-wide rotation plus each sheet's own printed scale.

Each physical sheet in this set carries its own "SCALE ___ FT. TO ONE INCH"
bar -- sheets 2 and 3 (dense downtown blocks) are printed at 50 ft/inch,
sheets 4 and 5 (sparser campus/outskirts) at 100 ft/inch. These were measured
directly off each sheet's printed bar (in px, at this TIFF's resolution) and
are NOT interchangeable -- using one sheet's scale for another was the
dominant source of error in the first version of this pipeline (positions
were off by 50-100%+ of the correct distance from the anchor).

The first version of this script also had the image-to-world rotation
backwards (wrong sign), compounding the scale bug into large, visibly
wrong placements, especially far from each sheet's anchor point. Both bugs
were caught by comparing the deployed map against present-day aerial
imagery and re-deriving the transform from two independently-geocoded
landmarks per sheet rather than trusting a single hand-read compass-rose
angle.

This is coarser than El Paso's per-sheet GeoTIFF alignment: expect
block-level accuracy (validated to within ~5m at the check points used),
not parcel-level. counts_by_type and sheets_digitized in city_summary.json
still carry the digitization-coverage caveat described in the repo root
README.
"""
import math

# Single town-wide rotation, solved from two independent two-landmark
# correspondences (sheet 2: Hotel Holland + Brewster County Courthouse;
# sheet 3: First Baptist Church + First Methodist Church), which agreed
# with each other to within ~2 degrees.
ROTATION_DEG = -21.8

# Per-sheet printed scale, measured directly off each sheet's own scale bar.
SCALE_50_M_PER_PX = 0.051056   # sheets 2, 3: "50 ft. to one inch"
SCALE_100_M_PER_PX = 0.10211   # sheets 4, 5: "100 ft. to one inch"

_theta = math.radians(ROTATION_DEG)
_cosT, _sinT = math.cos(_theta), math.sin(_theta)


def offset_latlon(anchor_latlon, anchor_px, target_px, scale_m_per_px):
    """Pixel offset from a sheet's anchor -> (lat, lon) of target_px.

    scale_m_per_px must be the correct per-sheet value (SCALE_50_M_PER_PX or
    SCALE_100_M_PER_PX) -- this is sheet-specific, not global.
    """
    lat0, lon0 = anchor_latlon
    a, b = scale_m_per_px * _cosT, scale_m_per_px * _sinT
    dx = target_px[0] - anchor_px[0]
    dy = target_px[1] - anchor_px[1]
    right_img, up_img = dx, -dy
    east_m = right_img * a + up_img * b
    north_m = up_img * a - right_img * b
    m_per_deg_lat = 111320.0
    m_per_deg_lon = 111320.0 * math.cos(math.radians(lat0))
    return (lat0 + north_m / m_per_deg_lat, lon0 + east_m / m_per_deg_lon)


# Per-sheet anchors: (pixel xy on that sheet's full-res master TIFF,
# real-world lat/lon of the same landmark today, that sheet's own scale).
ANCHORS = {
    2: {"landmark": "Hotel Holland",                 "px": (3300, 5600), "latlon": (30.3574016, -103.6628597), "scale": SCALE_50_M_PER_PX},
    3: {"landmark": "First Baptist Church of Alpine", "px": (1730, 2600), "latlon": (30.3594246, -103.6611778), "scale": SCALE_50_M_PER_PX},
    4: {"landmark": "Sul Ross Administration Bldg. (Lawrence Hall)", "px": (1630, 730), "latlon": (30.36207, -103.64925), "scale": SCALE_100_M_PER_PX},
    5: {"landmark": "St. James Episcopal Mission",    "px": (2660, 5295), "latlon": (30.3612632, -103.6640704), "scale": SCALE_100_M_PER_PX},
}
