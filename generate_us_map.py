"""One-time script to generate a Mercator-projected US map background PNG.

This creates a clean map of the continental US with state boundaries,
matching the Web Mercator projection used by pptx_exporter.py.

Usage:
    python generate_us_map.py

Outputs:
    static/img/us_map_bg.png
"""

import json
import math
import os
import urllib.request

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.collections import PatchCollection

# ---- Bounds matching pptx_exporter.py ----
LAT_MIN = 24.0
LAT_MAX = 50.0
LNG_MIN = -125.0
LNG_MAX = -66.0


def lat_to_mercator_y(lat):
    """Convert latitude to Web Mercator Y."""
    lat_rad = math.radians(lat)
    return math.log(math.tan(math.pi / 4 + lat_rad / 2))


MERC_Y_MIN = lat_to_mercator_y(LAT_MIN)
MERC_Y_MAX = lat_to_mercator_y(LAT_MAX)
MERC_Y_RANGE = MERC_Y_MAX - MERC_Y_MIN
LNG_RANGE = LNG_MAX - LNG_MIN


def lnglat_to_xy(lng, lat):
    """Convert (lng, lat) to normalized (x, y) on [0,1]."""
    x = (lng - LNG_MIN) / LNG_RANGE
    merc_y = lat_to_mercator_y(lat)
    y = 1.0 - (merc_y - MERC_Y_MIN) / MERC_Y_RANGE
    return x, y


def fetch_us_states_geojson():
    """Fetch US states GeoJSON from the US Census Bureau."""
    url = (
        "https://raw.githubusercontent.com/PublicaMundi/"
        "MappingAPI/master/data/geojson/us-states.json"
    )
    print(f"Fetching US states GeoJSON from: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Python"})
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
    print(f"  Loaded {len(data['features'])} states")
    return data


# Territories and non-continental states to exclude
EXCLUDE_STATES = {
    "Alaska", "Hawaii", "Puerto Rico", "Guam",
    "U.S. Virgin Islands", "American Samoa",
    "Northern Mariana Islands",
}


def extract_polygons(geojson):
    """Extract polygon coordinate lists for continental US states."""
    polygons = []
    for feature in geojson["features"]:
        name = feature["properties"].get("name", "")
        if name in EXCLUDE_STATES:
            continue

        geom = feature["geometry"]
        if geom["type"] == "Polygon":
            for ring in geom["coordinates"]:
                polygons.append(ring)
        elif geom["type"] == "MultiPolygon":
            for polygon in geom["coordinates"]:
                for ring in polygon:
                    polygons.append(ring)

    return polygons


def generate_map(output_path):
    """Generate the US map background PNG."""
    geojson = fetch_us_states_geojson()
    raw_polygons = extract_polygons(geojson)

    print(f"  Processing {len(raw_polygons)} polygon rings")

    # Convert to Mercator-projected normalized coordinates
    patches = []
    for ring in raw_polygons:
        projected = []
        for lng, lat in ring:
            # Clip to bounds
            if lat < LAT_MIN - 2 or lat > LAT_MAX + 2:
                continue
            if lng < LNG_MIN - 2 or lng > LNG_MAX + 2:
                continue
            x, y = lnglat_to_xy(lng, lat)
            projected.append((x, y))

        if len(projected) >= 3:
            patches.append(MplPolygon(projected, closed=True))

    print(f"  Created {len(patches)} matplotlib patches")

    # Create figure matching widescreen aspect ratio (13.333 : 7.5)
    fig_width = 19.2  # inches (high res at 100 dpi = 1920px)
    fig_height = fig_width * (7.5 / 13.333)
    fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height))

    # Style: light background with subtle grey state borders
    fig.patch.set_facecolor("#f8f9fa")
    ax.set_facecolor("#f8f9fa")

    # Draw state polygons
    collection = PatchCollection(
        patches,
        facecolor="#e9ecef",  # Light grey fill
        edgecolor="#adb5bd",  # Medium grey borders
        linewidth=0.8,
        alpha=1.0,
    )
    ax.add_collection(collection)

    # Set axis to exact [0,1] range (our normalized projection space)
    ax.set_xlim(0, 1)
    ax.set_ylim(1, 0)  # Inverted Y (top=north)
    ax.set_aspect("auto")
    ax.axis("off")

    # Remove all margins
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(
        output_path,
        dpi=100,
        bbox_inches="tight",
        pad_inches=0,
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)

    file_size = os.path.getsize(output_path)
    print(f"  Saved to: {output_path} ({file_size / 1024:.0f} KB)")


if __name__ == "__main__":
    output = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "static", "img", "us_map_bg.png",
    )
    generate_map(output)
    print("Done!")
