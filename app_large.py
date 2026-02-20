import os
import uuid
from flask import Flask, render_template, request, jsonify
from data_processor_large import parse_csv, process_provider_data

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8051))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
