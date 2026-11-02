"""
Downsample each 1908 Sanborn sheet GeoTIFF into a web-sized JPEG and compute
its lat/lon bounding box, for use as a Leaflet L.imageOverlay historic basemap
layer in index.html.
"""
import json, glob, os
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.enums import Resampling
from PIL import Image, ImageFilter
import numpy as np

SHEETS_DIR = 'sheets_1908'
OUT_DIR = 'site/sanborn'
MAX_DIM = 2600  # longest side, px -- raised for legibility of printed labels when zoomed in
WEBP_QUALITY = 82

os.makedirs(OUT_DIR, exist_ok=True)

def sheet_num_from_path(p):
    base = os.path.basename(p)
    return int(base.split('_')[1])

tifs = sorted(glob.glob(f"{SHEETS_DIR}/sheet_*.tif"), key=sheet_num_from_path)
manifest = []

for tif in tifs:
    n = sheet_num_from_path(tif)
    ds = rasterio.open(tif)
    w, h = ds.width, ds.height
    scale = min(1.0, MAX_DIM / max(w, h))
    out_w, out_h = max(1, int(w * scale)), max(1, int(h * scale))

    # read downsampled (first 3 bands as RGB; drop alpha if present)
    count = min(ds.count, 3)
    arr = ds.read(
        indexes=list(range(1, count + 1)),
        out_shape=(count, out_h, out_w),
        resampling=Resampling.bilinear
    )
    arr = np.transpose(arr, (1, 2, 0))
    if count == 1:
        arr = np.repeat(arr, 3, axis=2)

    # the scanned sheet is a rotated parchment page sitting in a black (0,0,0)
    # nodata-padded canvas -- make that padding transparent so overlapping
    # sheets don't show ugly black diamonds, and only the true scan shows.
    # Erode the mask a couple px and feather it so the antialiased black/parchment
    # boundary pixels (which are neither pure black nor true page color) don't
    # leave a visible seam where sheets overlap.
    is_content = ~((arr[:, :, 0] == 0) & (arr[:, :, 1] == 0) & (arr[:, :, 2] == 0))
    alpha_img = Image.fromarray(np.where(is_content, 255, 0).astype(np.uint8), mode='L')
    alpha_img = alpha_img.filter(ImageFilter.MinFilter(5))   # erode ~2px to drop antialiased ring
    alpha_img = alpha_img.filter(ImageFilter.GaussianBlur(1.2))  # feather the remaining edge
    alpha = np.array(alpha_img)
    rgba = np.dstack([arr, alpha])
    img = Image.fromarray(rgba, mode='RGBA')

    out_path = f"{OUT_DIR}/sheet_{n}.webp"
    img.save(out_path, 'WEBP', quality=WEBP_QUALITY, method=6)

    # geographic bounds (corners) -> bounding box in EPSG:4326
    b = ds.bounds
    xs = [b.left, b.right, b.left, b.right]
    ys = [b.bottom, b.bottom, b.top, b.top]
    lons, lats = warp_transform(ds.crs, 'EPSG:4326', xs, ys)
    west, east = min(lons), max(lons)
    south, north = min(lats), max(lats)

    manifest.append({
        'sheet': n,
        'file': f"sanborn/sheet_{n}.webp",
        'bounds': [[south, west], [north, east]]  # Leaflet LatLngBounds order
    })
    size_kb = os.path.getsize(out_path) / 1024
    print(f"sheet {n}: {out_w}x{out_h} -> {size_kb:.0f} KB  bounds=({south:.5f},{west:.5f})-({north:.5f},{east:.5f})")

with open(f"{OUT_DIR}/manifest.json", 'w') as fh:
    json.dump(manifest, fh)

total_mb = sum(os.path.getsize(f"{OUT_DIR}/sheet_{m['sheet']}.webp") for m in manifest) / 1024 / 1024
print(f"\nWrote {len(manifest)} sheet overlays, total {total_mb:.1f} MB")
