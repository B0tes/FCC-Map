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


def parse_csv(filepath):
    """Read an FCC BDC CSV file into a DataFrame."""
    df = pd.read_csv(filepath, dtype={"h3_res8_id": str, "technology": int})
    return df


def h3_to_geojson_polygon(h3_index):
    """Convert an H3 index to a GeoJSON Polygon geometry.

    h3.cell_to_boundary returns (lat, lng) tuples;
    GeoJSON requires [lng, lat] ordering.
    """
    boundary = h3.cell_to_boundary(h3_index)
    # Convert (lat, lng) -> [lng, lat] and close the ring
    coords = [[lng, lat] for lat, lng in boundary]
    coords.append(coords[0])
    return {"type": "Polygon", "coordinates": [coords]}


def process_provider_data(df):
    """Process a DataFrame of FCC BDC data into GeoJSON.

    Deduplicates by H3 cell, keeping the highest download speed per cell.
    Returns a dict with provider info and GeoJSON FeatureCollection.
    """
    # Extract provider info
    brand_name = df["brand_name"].iloc[0]
    states = sorted(df["state_usps"].unique().tolist())

    # Deduplicate: for each H3 cell, keep the row with the highest download speed.
    # Also track which technologies and location count per cell.
    agg = (
        df.groupby("h3_res8_id")
        .agg(
            max_download=("max_advertised_download_speed", "max"),
            max_upload=("max_advertised_upload_speed", "max"),
            technology=("technology", lambda x: x.mode().iloc[0]),
            location_count=("location_id", "nunique"),
            brand_name=("brand_name", "first"),
        )
        .reset_index()
    )

    # Build tech breakdown for metadata
    tech_counts = df.groupby("technology")["h3_res8_id"].nunique().to_dict()
    tech_breakdown = {
        TECH_LABELS.get(k, f"Unknown ({k})"): v for k, v in tech_counts.items()
    }

    # Build GeoJSON features
    features = []
    for _, row in agg.iterrows():
        h3_id = row["h3_res8_id"]
        if not h3.is_valid_cell(h3_id):
            continue

        tech_code = int(row["technology"])
        feature = {
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
            },
        }
        features.append(feature)

    geojson = {"type": "FeatureCollection", "features": features}

    # Compute bounding box from H3 cell centers
    lats, lngs = [], []
    for _, row in agg.iterrows():
        h3_id = row["h3_res8_id"]
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
        "total_hexes": len(features),
        "total_locations": int(df["location_id"].nunique()),
        "tech_breakdown": tech_breakdown,
        "geojson": geojson,
        "bounds": bounds,
    }
