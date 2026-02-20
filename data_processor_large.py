import pandas as pd
import h3
import json


TECH_LABELS = {
    10: "Copper/DSL",
    40: "Coaxial Cable/HFC",
    50: "Fiber (FTTP)",
    60: "Satellite",
    70: "Fixed Wireless",
    71: "Licensed Fixed Wireless",
    72: "Licensed-by-Rule Fixed Wireless",
}

TECH_CATEGORIES = {
    10: "copper",
    40: "cable",
    50: "fiber",
    60: "satellite",
    70: "wireless",
    71: "wireless",
    72: "wireless",
}

# H3 resolutions to pre-compute.
# The frontend swaps between these based on map zoom level.
#   zoom <= 7  → res 5  (~10km edge)
#   zoom <= 9  → res 6  (~3.7km edge)
#   zoom <= 11 → res 7  (~1.4km edge)
#   zoom <= 13 → res 8  (~0.5km edge, raw data)
H3_RESOLUTIONS = [5, 6, 7, 8]


def parse_csv(filepath):
    """Read an FCC BDC CSV file into a DataFrame."""
    df = pd.read_csv(filepath, dtype={"h3_res8_id": str, "technology": int})
    return df


def h3_to_geojson_polygon(h3_index):
    """Convert an H3 index to a GeoJSON Polygon geometry."""
    boundary = h3.cell_to_boundary(h3_index)
    coords = [[lng, lat] for lat, lng in boundary]
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def _aggregate_at_resolution(df, res):
    """Aggregate the raw res-8 data up to a given H3 resolution.

    For res 8 this is just dedup; for lower res it groups child cells
    into their parent hex.
    """
    if res == 8:
        col = "h3_res8_id"
    else:
        col = f"h3_res{res}"
        df[col] = df["h3_res8_id"].apply(
            lambda x: h3.cell_to_parent(x, res) if h3.is_valid_cell(x) else None
        )
        df = df.dropna(subset=[col])

    agg = (
        df.groupby(col)
        .agg(
            max_download=("max_advertised_download_speed", "max"),
            max_upload=("max_advertised_upload_speed", "max"),
            technology=("technology", lambda x: x.mode().iloc[0]),
            location_count=("location_id", "nunique"),
            child_hex_count=("h3_res8_id", "nunique"),
            brand_name=("brand_name", "first"),
        )
        .reset_index()
        .rename(columns={col: "h3_id"})
    )
    return agg


def _build_geojson(agg):
    """Convert an aggregated DataFrame into a GeoJSON FeatureCollection."""
    features = []
    for _, row in agg.iterrows():
        h3_id = row["h3_id"]
        if not h3.is_valid_cell(h3_id):
            continue
        tech_code = int(row["technology"])
        features.append({
            "type": "Feature",
            "geometry": h3_to_geojson_polygon(h3_id),
            "properties": {
                "h3_id": h3_id,
                "brand_name": row["brand_name"],
                "technology": tech_code,
                "tech_label": TECH_LABELS.get(tech_code, f"Unknown ({tech_code})"),
                "tech_category": TECH_CATEGORIES.get(tech_code, "other"),
                "max_download": int(row["max_download"]),
                "max_upload": int(row["max_upload"]),
                "location_count": int(row["location_count"]),
                "child_hex_count": int(row["child_hex_count"]),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def process_provider_data(df):
    """Process FCC BDC data into GeoJSON at multiple H3 resolutions.

    Returns a dict with one GeoJSON FeatureCollection per resolution,
    keyed by resolution number (e.g. "5", "6", "7", "8").
    The frontend swaps the active layer as the user zooms.
    """
    brand_name = df["brand_name"].iloc[0]
    states = sorted(df["state_usps"].unique().tolist())

    # Tech breakdown (always counted at native res-8)
    tech_counts = df.groupby("technology")["h3_res8_id"].nunique().to_dict()
    tech_breakdown = {
        TECH_LABELS.get(k, f"Unknown ({k})"): v for k, v in tech_counts.items()
    }

    # Pre-compute GeoJSON for each resolution
    geojson_by_res = {}
    hex_counts = {}
    for res in H3_RESOLUTIONS:
        agg = _aggregate_at_resolution(df.copy(), res)
        geojson_by_res[str(res)] = _build_geojson(agg)
        hex_counts[str(res)] = len(agg)

    # Bounding box from the res-8 data
    lats, lngs = [], []
    for h3_id in df["h3_res8_id"].unique():
        if h3.is_valid_cell(h3_id):
            lat, lng = h3.cell_to_latlng(h3_id)
            lats.append(lat)
            lngs.append(lng)

    bounds = None
    if lats and lngs:
        bounds = [[min(lats), min(lngs)], [max(lats), max(lngs)]]

    return {
        "brand_name": brand_name,
        "states": states,
        "total_locations": int(df["location_id"].nunique()),
        "tech_breakdown": tech_breakdown,
        "geojson_by_res": geojson_by_res,
        "hex_counts": hex_counts,
        "bounds": bounds,
    }
