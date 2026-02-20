import os
import uuid
from flask import Flask, render_template, request, jsonify, send_file
from data_processor_large import parse_csv, process_provider_data
from pptx_exporter import generate_pptx, apply_filters

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "uploads")
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max upload

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# In-memory store of processed provider data
providers = {}

# Color palette for providers
PROVIDER_COLORS = [
    "#e74c3c",  # red
    "#3498db",  # blue
    "#2ecc71",  # green
    "#f39c12",  # orange
    "#9b59b6",  # purple
    "#1abc9c",  # teal
    "#e67e22",  # dark orange
    "#34495e",  # dark blue-grey
    "#e91e63",  # pink
    "#00bcd4",  # cyan
]


def get_next_color():
    idx = len(providers) % len(PROVIDER_COLORS)
    return PROVIDER_COLORS[idx]


@app.route("/")
def index():
    return render_template("index_large.html")


@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.endswith(".csv"):
        return jsonify({"error": "Only CSV files are supported"}), 400

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    try:
        df = parse_csv(filepath)
        result = process_provider_data(df)

        provider_id = uuid.uuid4().hex[:8]
        color = get_next_color()

        providers[provider_id] = {
            "id": provider_id,
            "brand_name": result["brand_name"],
            "color": color,
            "states": result["states"],
            "total_locations": result["total_locations"],
            "tech_breakdown": result["tech_breakdown"],
            "hex_counts": result["hex_counts"],
            "bounds": result["bounds"],
            "filename": file.filename,
            "geojson_by_res": result["geojson_by_res"],
        }

        return jsonify(
            {
                "id": provider_id,
                "brand_name": result["brand_name"],
                "color": color,
                "states": result["states"],
                "total_locations": result["total_locations"],
                "tech_breakdown": result["tech_breakdown"],
                "hex_counts": result["hex_counts"],
                "bounds": result["bounds"],
                "geojson_by_res": result["geojson_by_res"],
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)


@app.route("/api/providers", methods=["GET"])
def list_providers():
    return jsonify(list(providers.values()))


@app.route("/api/providers/<provider_id>", methods=["DELETE"])
def delete_provider(provider_id):
    if provider_id in providers:
        del providers[provider_id]
        return jsonify({"status": "deleted"})
    return jsonify({"error": "Provider not found"}), 404


@app.route("/api/export-pptx", methods=["POST"])
def export_pptx():
    """Export visible providers' hex data as a PPTX file."""
    data = request.get_json()
    if not data or "providers" not in data:
        return jsonify({"error": "Missing providers list"}), 400

    requested = data["providers"]
    tech_filters = set(data.get("tech_filters", [
        "fiber", "cable", "copper", "wireless", "satellite"
    ]))
    min_speed = data.get("min_speed", 0)

    provider_data_list = []
    for item in requested:
        pid = item.get("id")
        color = item.get("color", "#999999")

        if pid not in providers:
            continue

        prov = providers[pid]
        geojson_by_res = prov.get("geojson_by_res", {})
        geojson_res5 = geojson_by_res.get("5")
        if not geojson_res5:
            continue

        filtered = apply_filters(geojson_res5, tech_filters, min_speed)

        provider_data_list.append({
            "geojson": filtered,
            "color": color,
            "brand_name": prov["brand_name"],
        })

    if not provider_data_list:
        return jsonify({"error": "No matching data to export"}), 400

    bg_path = os.path.join(
        os.path.dirname(__file__), "static", "img", "us_map_bg.png"
    )
    bg_image = bg_path if os.path.exists(bg_path) else None

    output = generate_pptx(provider_data_list, bg_image_path=bg_image)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        as_attachment=True,
        download_name="fcc_coverage_export.pptx",
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8051))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
