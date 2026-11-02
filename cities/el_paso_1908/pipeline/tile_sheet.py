"""
Tile a georeferenced Sanborn GeoTIFF into overlapping crops for visual label
extraction, and provide pixel->lon/lat conversion using the raster's own
affine transform (no bbox-corner approximation).

Usage: python3 tile_sheet.py <input.tif> <output_dir> [--tile 1600] [--overlap 200]
"""
import sys, os, json, argparse
from PIL import Image
import rasterio
from rasterio.warp import transform as warp_transform

Image.MAX_IMAGE_PIXELS = None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('input_tif')
    ap.add_argument('output_dir')
    ap.add_argument('--tile', type=int, default=1600)
    ap.add_argument('--overlap', type=int, default=200)
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    ds = rasterio.open(args.input_tif)
    w, h = ds.width, ds.height
    crs = ds.crs
    transform = ds.transform

    im = Image.open(args.input_tif)

    step = args.tile - args.overlap
    tiles = []
    y = 0
    tidx = 0
    while y < h:
        x = 0
        while x < w:
            x1 = min(x + args.tile, w)
            y1 = min(y + args.tile, h)
            crop = im.crop((x, y, x1, y1))
            # skip near-blank tiles (mostly white/cream background)
            thumb = crop.convert('L').resize((32,32))
            extrema = thumb.getextrema()
            px = list(thumb.getdata())
            nonwhite = sum(1 for v in px if v < 235)
            if nonwhite < 15:  # almost entirely blank
                x += step
                continue
            fname = f"tile_{tidx:03d}_x{x}_y{y}.png"
            crop.save(os.path.join(args.output_dir, fname))
            # compute geo bounds of this tile using the raster transform
            lon0, lat0 = transform * (x, y)
            lon1, lat1 = transform * (x1, y1)
            # transform is in EPSG:3857; convert to WGS84
            (lons, lats) = warp_transform(crs, 'EPSG:4326', [lon0, lon1], [lat0, lat1])
            tiles.append({
                'file': fname,
                'px_bounds': [x, y, x1, y1],
                'lon_range': [min(lons), max(lons)],
                'lat_range': [min(lats), max(lats)],
            })
            tidx += 1
            x += step
        y += step

    with open(os.path.join(args.output_dir, 'tile_index.json'), 'w') as f:
        json.dump({
            'source': args.input_tif,
            'width': w, 'height': h,
            'crs': str(crs),
            'tiles': tiles
        }, f, indent=1)
    print(f"Wrote {len(tiles)} non-blank tiles to {args.output_dir}")

if __name__ == '__main__':
    main()
