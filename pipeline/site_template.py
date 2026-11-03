"""
Shared city-site generator for The Lodging Ledger.

Phase 1 (build_city.py) always renders with geocode_status="pending" --
the honest pending-geocode banner + per-marker badge is baked in by default,
not something you have to remember to add. Phase 2 (refine_geocoding.py)
re-renders the SAME city with geocode_status="complete" once a validated
transform exists, which drops the banner/badge automatically. There should
be no third path where someone hand-writes a city's index.html again.

sheets_manifest: path (relative to the site dir) to a sanborn/manifest.json
  of {"file","topleft","topright","bottomleft"} entries, as built by
  Alpine's/El Paso's tiling step -- or None if sheet images haven't been
  tiled/placed for this city yet (phase 1 normally has no sheets yet).
"""

TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{city_label} {year} — The Lodging Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Special+Elite&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
{rotated_overlay_script}
<style>
:root {{
  --parchment: #EAE3D2; --parchment-deep: #DFD6BF; --ink: #2B2420; --ink-soft: #5B5245;
  --rust: #A6531C; --slate: #3D5A6C; --line: #C9BC9E; --paper-card: #F3EEE1;
  color-scheme: light;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --parchment: #1C1812; --parchment-deep: #15110D; --ink: #E9E1CD;
    --ink-soft: #B8AD93; --rust: #D97B3F; --slate: #7FA5BC;
    --line: #3A3326; --paper-card: #231E17; color-scheme: dark;
  }}
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background: var(--parchment-deep); color: var(--ink); font-family:'IBM Plex Mono',ui-monospace,monospace; padding:24px 16px; }}
.wrap {{
  max-width: 1320px; margin: 0 auto;
  background-image: linear-gradient(var(--line) 1px, transparent 1px), linear-gradient(90deg, var(--line) 1px, transparent 1px);
  background-size: 28px 28px; background-color: var(--parchment);
  border: 1px solid var(--line); box-shadow: 0 12px 40px rgba(0,0,0,0.25);
}}
header {{ padding: 28px 32px 20px; border-bottom: 2px solid var(--ink); display:flex; justify-content:space-between; align-items:flex-end; gap:16px; flex-wrap:wrap; }}
header a.back {{ font-size:0.7rem; color: var(--ink-soft); text-decoration:none; }}
header h1 {{ font-family:'Special Elite','IBM Plex Mono',monospace; font-size:clamp(1.4rem,1.1rem+1.4vw,2.1rem); margin:4px 0 4px; }}
header .sub {{ color: var(--ink-soft); font-size:0.8rem; max-width:58ch; line-height:1.5; }}
header .plate {{ font-family:'Special Elite',monospace; font-size:0.7rem; color:var(--ink-soft); text-align:right; line-height:1.6; border:1px solid var(--line); padding:8px 12px; background:var(--paper-card); }}
.note-banner {{ padding:10px 32px; font-size:0.72rem; color:var(--ink-soft); background:var(--paper-card); border-bottom:1px solid var(--line); line-height:1.5; }}
.note-banner.pending {{ color:#8a4b12; }}
@media (prefers-color-scheme: dark) {{ .note-banner.pending {{ color:#e3a05c; }} }}
.pending-tag {{ display:inline-block; font-size:0.62rem; text-transform:uppercase; letter-spacing:0.04em; border:1px solid #a6531c; color:#a6531c; padding:1px 5px; border-radius:2px; margin-top:4px; }}
.body-grid {{ display:grid; grid-template-columns: minmax(0,1fr) 320px; }}
@media (max-width:860px) {{ .body-grid {{ grid-template-columns:1fr; }} }}
.map-col {{ padding:20px; min-width:0; }}
.map-frame {{ border:1px solid var(--ink); }}
#map {{ height:min(78vh,880px); width:100%; background:var(--parchment-deep); filter:saturate(0.9); }}
@media (max-width:860px) {{ #map {{ height:60vh; }} }}
.legend {{ display:flex; flex-wrap:wrap; gap:10px 18px; padding:12px 4px 4px; font-size:0.72rem; }}
.legend .row {{ display:flex; align-items:center; gap:6px; color:var(--ink-soft); }}
.legend .dot {{ width:11px; height:11px; border-radius:50%; border:1.5px solid var(--ink); flex:none; }}
.sidebar {{ border-left:1px solid var(--ink); padding:20px; display:flex; flex-direction:column; gap:16px; min-width:0; }}
@media (max-width:860px) {{ .sidebar {{ border-left:none; border-top:1px solid var(--ink); }} }}
.card {{ background:var(--paper-card); border:1px solid var(--line); padding:14px 16px; }}
.card h2 {{ font-family:'Special Elite',monospace; font-size:0.95rem; margin:0 0 8px; display:flex; align-items:center; gap:8px; }}
.card h2::before {{ content:""; width:6px; height:6px; background:var(--rust); display:inline-block; }}
.card p {{ font-size:0.78rem; line-height:1.55; color:var(--ink-soft); margin:0; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(100px,1fr)); gap:1px; background:var(--ink); }}
.stat {{ background:var(--paper-card); padding:10px 12px; text-align:center; }}
.stat .n {{ font-size:1.3rem; font-weight:700; color:var(--rust); font-variant-numeric:tabular-nums; }}
.stat .l {{ font-size:0.6rem; text-transform:uppercase; letter-spacing:0.07em; color:var(--ink-soft); margin-top:2px; }}
.stamp {{ text-align:center; font-size:0.64rem; color:var(--ink-soft); border:1px dashed var(--line); padding:8px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <a class="back" href="../../../index.html">&larr; all cities</a>
      <h1>{city_label}, {state_full} &middot; {survey_date}</h1>
      <div class="sub">{about_sub}</div>
    </div>
    <div class="plate">SANBORN MAP CO.<br>{sheets} SHEETS &middot; {scale_label}<br>SURVEYED {survey_date_caps}</div>
  </header>
  {note_banner}
  <div class="stats" id="stats"></div>
  <div class="body-grid">
    <div class="map-col">
      <div class="map-frame"><div id="map"></div></div>
      <div class="legend" id="legend"></div>
    </div>
    <div class="sidebar">
      <div class="card">
        <h2>About</h2>
        <p>{about_text}</p>
      </div>
      <div class="card">
        <h2>Source</h2>
        <p>{source_text}</p>
      </div>
      <div class="stamp">Part of The Lodging Ledger &middot; hoffmanap/SRO</div>
    </div>
  </div>
</div>
<script>
var TYPES = {{
  hotel:                 {{ label: "Hotel",                     color: "#A6531C" }},
  boarding:              {{ label: "Boarding House",            color: "#3D5A6C" }},
  lodging:               {{ label: "Lodgings",                  color: "#8A7B4E" }},
  tenement:              {{ label: "Tenement",                  color: "#6B3F3F" }},
  apartments:            {{ label: "Apartments",                color: "#4E7A5C" }},
  institutional_lodging: {{ label: "Institutional (Y.M.C.A.)",   color: "#5B5245" }}
}};
function typeInfo(t) {{ return TYPES[t] || {{ label: t.replace(/_/g,' '), color: "#8A7B4E" }}; }}

var map = L.map('map', {{ scrollWheelZoom:false }}).setView([{center_lat}, {center_lon}], {zoom});
var aerial = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
  maxZoom: 19, attribution: 'Esri World Imagery'
}}).addTo(map);
var streets = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'
}});
{sheets_js}

fetch('../{geojson_file}', {{ cache:'reload' }})
  .then(function(r){{ return r.json(); }})
  .then(function(fc) {{
    var markersByType = {{}};
    fc.features.forEach(function(f) {{
      var t = f.properties.building_type;
      var info = typeInfo(t);
      var m = L.circleMarker([f.geometry.coordinates[1], f.geometry.coordinates[0]], {{
        radius: 7, color:'#2B2420', weight:1.5, fillColor: info.color, fillOpacity:0.9
      }}).bindPopup(
        '<strong>' + f.properties.label + '</strong><br>' +
        info.label + '<br>' +
        '<span style="color:#5B5245;font-size:0.85em">' + f.properties.note + '</span><br>' +
        '<span style="color:#5B5245;font-size:0.8em">Sheet ' + f.properties.sheet + ' &middot; ' + f.properties.year + '</span><br>' +
        (f.properties.confidence === 'pending_precise_geocode'
          ? '<span class="pending-tag">&#9888; approximate position</span>'
          : '')
      );
      (markersByType[t] = markersByType[t] || []).push(m);
      m.addTo(map);
    }});

    var legend = document.getElementById('legend');
    Object.keys(markersByType).sort().forEach(function(t) {{
      var info = typeInfo(t);
      var row = document.createElement('span');
      row.className = 'row';
      row.innerHTML = '<span class="dot" style="background:' + info.color + ';"></span>' + info.label + ' (' + markersByType[t].length + ')';
      legend.appendChild(row);
    }});

    var stats = document.getElementById('stats');
    var total = fc.features.length;
    var byType = {{}};
    fc.features.forEach(function(f){{ byType[f.properties.building_type] = (byType[f.properties.building_type]||0)+1; }});
    function stat(n,l) {{
      var d = document.createElement('div');
      d.className = 'stat';
      d.innerHTML = '<div class="n">' + n + '</div><div class="l">' + l + '</div>';
      stats.appendChild(d);
    }}
    stat({sheets}, 'Sheets Digitized');
    stat(total, 'Structures Recorded');
    stat(byType.hotel||0, 'Hotels');
    stat(byType.boarding||0, 'Boarding Hses.');
  }});
</script>
</body>
</html>
"""

PENDING_BANNER = """<div class="note-banner pending">
    <strong>&#9888; Geocoding pending:</strong> the {n} buildings below are correctly <em>identified and typed</em> from the original sheets, but are currently placed only by nearest cross-street (approximate, block-level-or-worse). A proper per-sheet georeferencing pass for {city_label} hasn't been done yet -- it runs later, across all pending cities in one sweep (see pipeline/refine_geocoding.py). Treat marker positions here as rough; the building list, types, and counts are solid. Source: Library of Congress raw sheet scans (via the LC Labs bulk Sanborn dataset), read tile-by-tile by eye.
  </div>"""

COMPLETE_BANNER = """<div class="note-banner">
    Building positions are from a validated per-sheet pixel transform (control points cross-checked against an independent third landmark). Source: Library of Congress raw sheet scans (via the LC Labs bulk Sanborn dataset), read tile-by-tile by eye.
  </div>"""

ROTATED_OVERLAY_SCRIPT = '<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet.imageoverlay.rotated/0.1.0/Leaflet.ImageOverlay.Rotated.min.js"></script>'

SHEETS_JS = """
var sheetLayer = L.layerGroup();
fetch('sanborn/manifest.json', {{ cache:'reload' }})
  .then(function(r){{ return r.json(); }})
  .then(function(manifest) {{
    manifest.forEach(function(m) {{
      var overlay = L.imageOverlay.rotated('sanborn/' + m.file, L.latLng(m.topleft), L.latLng(m.topright), L.latLng(m.bottomleft), {{
        opacity: 0.75, interactive: false
      }});
      overlay.addTo(sheetLayer);
    }});
    sheetLayer.addTo(map);
  }});
L.control.layers({{ "Aerial": aerial, "Streets": streets }}, {{ "{sheet_label} Sanborn sheets": sheetLayer }}, {{ collapsed:false }}).addTo(map);
"""

NO_SHEETS_JS = """
L.control.layers({ "Aerial": aerial, "Streets": streets }, {}, { collapsed:false }).addTo(map);
"""


def render_site(*, city_label, state_full, survey_date, sheets, scale_label,
                 about_sub, about_text, source_text, center_lat, center_lon,
                 zoom, geojson_file, n_buildings, geocode_status="pending",
                 has_sheets=False, sheet_label=None, year=None):
    """geocode_status: "pending" or "complete". has_sheets: whether a
    sanborn/manifest.json exists in the site dir (sheet image overlays)."""
    note_banner = PENDING_BANNER.format(n=n_buildings, city_label=city_label) \
        if geocode_status == "pending" else COMPLETE_BANNER
    if has_sheets:
        sheets_js = SHEETS_JS.format(sheet_label=sheet_label or str(year or ""))
        overlay_script = ROTATED_OVERLAY_SCRIPT
    else:
        sheets_js = NO_SHEETS_JS
        overlay_script = ""
    return TEMPLATE.format(
        city_label=city_label, state_full=state_full, survey_date=survey_date,
        survey_date_caps=survey_date.upper(), sheets=sheets, scale_label=scale_label,
        about_sub=about_sub, about_text=about_text, source_text=source_text,
        center_lat=center_lat, center_lon=center_lon, zoom=zoom,
        geojson_file=geojson_file, note_banner=note_banner,
        sheets_js=sheets_js, rotated_overlay_script=overlay_script,
        year=year or "",
    )
