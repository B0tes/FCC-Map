// ---- State ----
const providerData = {}; // id -> { geojson_by_res, color, visible, meta, activeLayers }
let activeTechFilters = new Set(["fiber", "cable", "copper", "wireless", "satellite"]);
let minSpeed = 0;
let currentH3Res = 5; // tracks which resolution is currently displayed

// ---- Zoom → H3 resolution mapping ----
// Matches the FCC broadband map behavior:
//   zoom <= 7  → H3 res 5  (~10km edge, big hexes)
//   zoom <= 9  → H3 res 6  (~3.7km edge)
//   zoom <= 11 → H3 res 7  (~1.4km edge)
//   zoom > 11  → H3 res 8  (~0.5km edge, full detail)
function getH3ResForZoom(zoom) {
    if (zoom <= 7) return 5;
    if (zoom <= 9) return 6;
    if (zoom <= 11) return 7;
    return 8;
}

// ---- Map Setup ----
const map = L.map("map", {
    center: [39.8, -98.5],
    zoom: 5,
    zoomControl: true,
});

L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 19,
}).addTo(map);

// ---- Zoom indicator ----
const zoomInfo = document.getElementById("zoom-info");
const zoomLevel = document.getElementById("zoom-level");
const hexLevel = document.getElementById("hex-level");

function updateZoomIndicator() {
    const zoom = map.getZoom();
    const h3Res = getH3ResForZoom(zoom);
    if (zoomLevel) zoomLevel.textContent = zoom.toFixed(1);
    if (hexLevel) hexLevel.textContent = h3Res;
}
updateZoomIndicator();

// ---- File Upload ----
const uploadArea = document.getElementById("upload-area");
const fileInput = document.getElementById("file-input");
const progressBar = document.getElementById("upload-progress");
const progressFill = progressBar.querySelector(".progress-fill");
const progressText = progressBar.querySelector(".progress-text");

uploadArea.addEventListener("click", () => fileInput.click());

uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", () => {
    uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    const files = Array.from(e.dataTransfer.files).filter((f) =>
        f.name.endsWith(".csv")
    );
    files.forEach(uploadFile);
});

fileInput.addEventListener("change", () => {
    Array.from(fileInput.files).forEach(uploadFile);
    fileInput.value = "";
});

function uploadFile(file) {
    const formData = new FormData();
    formData.append("file", file);

    progressBar.style.display = "flex";
    progressFill.style.width = "0%";
    progressText.textContent = `Processing ${file.name}...`;

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");

    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const pct = Math.round((e.loaded / e.total) * 50);
            progressFill.style.width = pct + "%";
            progressText.textContent = `Uploading ${file.name}... ${pct * 2}%`;
        }
    };

    xhr.onload = () => {
        if (xhr.status === 200) {
            progressFill.style.width = "100%";
            progressText.textContent = "Done!";
            setTimeout(() => (progressBar.style.display = "none"), 1500);

            const data = JSON.parse(xhr.responseText);
            addProviderToMap(data);
        } else {
            const err = JSON.parse(xhr.responseText);
            progressText.textContent = `Error: ${err.error}`;
            progressFill.style.width = "100%";
            progressFill.style.background = "#e74c3c";
            setTimeout(() => {
                progressBar.style.display = "none";
                progressFill.style.background = "";
            }, 3000);
        }
    };

    xhr.onerror = () => {
        progressText.textContent = "Upload failed.";
        setTimeout(() => (progressBar.style.display = "none"), 3000);
    };

    progressFill.style.width = "50%";
    progressText.textContent = `Processing ${file.name} on server...`;

    xhr.send(formData);
}

// ---- Popup builder ----
function buildPopup(p) {
    let html = `
        <div class="hex-popup">
            <strong>${p.brand_name}</strong><br>
            <b>Technology:</b> ${p.tech_label}<br>
            <b>Max Download:</b> ${p.max_download} Mbps<br>
            <b>Max Upload:</b> ${p.max_upload} Mbps<br>
            <b>Locations:</b> ${p.location_count}`;
    if (p.child_hex_count && p.child_hex_count > 1) {
        html += `<br><b>Detail hexes (res 8):</b> ${p.child_hex_count}`;
    }
    html += `</div>`;
    return html;
}

// ---- Feature filter ----
function shouldShowFeature(feature) {
    const p = feature.properties;
    if (!activeTechFilters.has(p.tech_category)) return false;
    if (p.max_download < minSpeed) return false;
    return true;
}

// ---- Create a Leaflet GeoJSON layer for a provider at a given resolution ----
function createLayer(provId, res) {
    const prov = providerData[provId];
    const geojson = prov.geojson_by_res[String(res)];
    if (!geojson) return null;

    return L.geoJSON(geojson, {
        style: () => ({
            fillColor: prov.color,
            fillOpacity: 0.5,
            color: prov.color,
            weight: 1,
            opacity: 0.8,
        }),
        onEachFeature: (feature, layer) => {
            layer.bindPopup(buildPopup(feature.properties));
        },
        filter: shouldShowFeature,
    });
}

// ---- Provider Layer Management ----
function addProviderToMap(data) {
    const h3Res = getH3ResForZoom(map.getZoom());

    providerData[data.id] = {
        geojson_by_res: data.geojson_by_res,
        color: data.color,
        visible: true,
        meta: data,
        activeLayer: null,
        activeRes: null,
    };

    // Create and show the layer for the current zoom
    const layer = createLayer(data.id, h3Res);
    if (layer) {
        layer.addTo(map);
        providerData[data.id].activeLayer = layer;
        providerData[data.id].activeRes = h3Res;
    }

    // Fit map to bounds
    if (data.bounds) {
        const allBounds = getAllBounds();
        map.fitBounds(allBounds, { padding: [50, 50] });
    }

    updateProviderList();
}

function getAllBounds() {
    let allLats = [];
    let allLngs = [];
    for (const id in providerData) {
        const b = providerData[id].meta.bounds;
        if (b) {
            allLats.push(b[0][0], b[1][0]);
            allLngs.push(b[0][1], b[1][1]);
        }
    }
    if (allLats.length === 0) return [[24, -125], [50, -66]];
    return [
        [Math.min(...allLats), Math.min(...allLngs)],
        [Math.max(...allLats), Math.max(...allLngs)],
    ];
}

// ---- Swap all provider layers to a new H3 resolution ----
function swapToResolution(newRes) {
    for (const id in providerData) {
        const prov = providerData[id];
        if (!prov.visible) continue;

        // Remove old layer
        if (prov.activeLayer) {
            map.removeLayer(prov.activeLayer);
        }

        // Create new layer at the target resolution
        const layer = createLayer(id, newRes);
        if (layer) {
            layer.addTo(map);
        }
        prov.activeLayer = layer;
        prov.activeRes = newRes;
    }
    currentH3Res = newRes;
}

// ---- Refresh layers at the current resolution (for filter changes) ----
function refreshAllLayers() {
    const h3Res = getH3ResForZoom(map.getZoom());
    for (const id in providerData) {
        const prov = providerData[id];
        if (!prov.visible) continue;

        if (prov.activeLayer) {
            map.removeLayer(prov.activeLayer);
        }
        const layer = createLayer(id, h3Res);
        if (layer) {
            layer.addTo(map);
        }
        prov.activeLayer = layer;
        prov.activeRes = h3Res;
    }
}

// ---- Listen to zoom changes and swap resolutions ----
map.on("zoomend", () => {
    updateZoomIndicator();
    const zoom = map.getZoom();
    const targetRes = getH3ResForZoom(zoom);
    if (targetRes !== currentH3Res) {
        swapToResolution(targetRes);
    }
});

map.on("zoom", () => {
    updateZoomIndicator();
});

// ---- Provider List UI ----
function updateProviderList() {
    const container = document.getElementById("provider-list");
    const ids = Object.keys(providerData);

    if (ids.length === 0) {
        container.innerHTML = '<p class="empty-state">No providers loaded yet.</p>';
        return;
    }

    container.innerHTML = ids
        .map((id) => {
            const prov = providerData[id];
            const d = prov.meta;
            const techInfo = Object.entries(d.tech_breakdown)
                .map(([k, v]) => `${k}: ${v.toLocaleString()} hexes`)
                .join("<br>");
            const hexInfo = Object.entries(d.hex_counts)
                .map(([res, count]) => `Res ${res}: ${count.toLocaleString()}`)
                .join(" &middot; ");

            return `
            <div class="provider-card">
                <div class="provider-header">
                    <span class="color-swatch" style="background:${d.color}"></span>
                    <strong>${d.brand_name}</strong>
                    <span class="provider-state">${d.states.join(", ")}</span>
                </div>
                <div class="provider-stats">
                    ${d.total_locations.toLocaleString()} locations
                </div>
                <div class="provider-tech">${techInfo}</div>
                <div class="provider-hex-counts">${hexInfo}</div>
                <div class="provider-actions">
                    <label class="toggle-label">
                        <input type="checkbox" ${prov.visible ? "checked" : ""}
                               onchange="toggleProvider('${id}', this.checked)">
                        Visible
                    </label>
                    <button class="btn-remove" onclick="removeProvider('${id}')">Remove</button>
                </div>
            </div>
        `;
        })
        .join("");
}

function toggleProvider(id, visible) {
    const prov = providerData[id];
    prov.visible = visible;
    if (visible) {
        const h3Res = getH3ResForZoom(map.getZoom());
        const layer = createLayer(id, h3Res);
        if (layer) {
            layer.addTo(map);
        }
        prov.activeLayer = layer;
        prov.activeRes = h3Res;
    } else {
        if (prov.activeLayer) {
            map.removeLayer(prov.activeLayer);
            prov.activeLayer = null;
        }
    }
}

function removeProvider(id) {
    const prov = providerData[id];
    if (prov) {
        if (prov.activeLayer) {
            map.removeLayer(prov.activeLayer);
        }
        delete providerData[id];
    }
    fetch(`/api/providers/${id}`, { method: "DELETE" });
    updateProviderList();
}

// ---- Filter Controls ----
document.querySelectorAll("#tech-filters input[type=checkbox]").forEach((cb) => {
    cb.addEventListener("change", () => {
        activeTechFilters = new Set(
            Array.from(
                document.querySelectorAll("#tech-filters input:checked")
            ).map((el) => el.value)
        );
        refreshAllLayers();
    });
});

const speedSlider = document.getElementById("speed-slider");
const speedLabel = document.getElementById("speed-label");

speedSlider.addEventListener("input", () => {
    minSpeed = parseInt(speedSlider.value);
    speedLabel.textContent = minSpeed + " Mbps";
});

speedSlider.addEventListener("change", () => {
    minSpeed = parseInt(speedSlider.value);
    speedLabel.textContent = minSpeed + " Mbps";
    refreshAllLayers();
});
