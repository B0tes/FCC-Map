// ---- State ----
const providerLayers = {}; // id -> { layer, data, visible }
let activeTechFilters = new Set(["fiber", "cable", "copper", "wireless", "satellite"]);
let minSpeed = 0;

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

    // Show indeterminate progress for server processing
    progressFill.style.width = "50%";
    progressText.textContent = `Processing ${file.name} on server...`;

    xhr.send(formData);
}

// ---- Provider Layer Management ----
function addProviderToMap(data) {
    const layer = L.geoJSON(data.geojson, {
        style: (feature) => ({
            fillColor: data.color,
            fillOpacity: 0.5,
            color: data.color,
            weight: 0.5,
            opacity: 0.7,
        }),
        onEachFeature: (feature, layer) => {
            const p = feature.properties;
            layer.bindPopup(`
                <div class="hex-popup">
                    <strong>${p.brand_name}</strong><br>
                    <b>Technology:</b> ${p.tech_label}<br>
                    <b>Max Download:</b> ${p.max_download} Mbps<br>
                    <b>Max Upload:</b> ${p.max_upload} Mbps<br>
                    <b>Locations in cell:</b> ${p.location_count}
                </div>
            `);
        },
        filter: (feature) => shouldShowFeature(feature),
    });

    layer.addTo(map);

    providerLayers[data.id] = {
        layer: layer,
        data: data,
        visible: true,
    };

    // Fit map to the data bounds
    if (data.bounds) {
        const allBounds = getAllBounds();
        map.fitBounds(allBounds, { padding: [50, 50] });
    }

    updateProviderList();
}

function getAllBounds() {
    let allLats = [];
    let allLngs = [];
    for (const id in providerLayers) {
        const b = providerLayers[id].data.bounds;
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

function shouldShowFeature(feature) {
    const p = feature.properties;
    if (!activeTechFilters.has(p.tech_category)) return false;
    if (p.max_download < minSpeed) return false;
    return true;
}

function refreshAllLayers() {
    for (const id in providerLayers) {
        const entry = providerLayers[id];
        if (!entry.visible) continue;

        // Remove and re-add with updated filter
        map.removeLayer(entry.layer);
        entry.layer = L.geoJSON(entry.data.geojson, {
            style: () => ({
                fillColor: entry.data.color,
                fillOpacity: 0.5,
                color: entry.data.color,
                weight: 0.5,
                opacity: 0.7,
            }),
            onEachFeature: (feature, layer) => {
                const p = feature.properties;
                layer.bindPopup(`
                    <div class="hex-popup">
                        <strong>${p.brand_name}</strong><br>
                        <b>Technology:</b> ${p.tech_label}<br>
                        <b>Max Download:</b> ${p.max_download} Mbps<br>
                        <b>Max Upload:</b> ${p.max_upload} Mbps<br>
                        <b>Locations in cell:</b> ${p.location_count}
                    </div>
                `);
            },
            filter: shouldShowFeature,
        });
        entry.layer.addTo(map);
    }
}

// ---- Provider List UI ----
function updateProviderList() {
    const container = document.getElementById("provider-list");
    const ids = Object.keys(providerLayers);

    if (ids.length === 0) {
        container.innerHTML = '<p class="empty-state">No providers loaded yet.</p>';
        return;
    }

    container.innerHTML = ids
        .map((id) => {
            const p = providerLayers[id];
            const d = p.data;
            const techInfo = Object.entries(d.tech_breakdown)
                .map(([k, v]) => `${k}: ${v.toLocaleString()} hexes`)
                .join("<br>");

            return `
            <div class="provider-card">
                <div class="provider-header">
                    <span class="color-swatch" style="background:${d.color}"></span>
                    <strong>${d.brand_name}</strong>
                    <span class="provider-state">${d.states.join(", ")}</span>
                </div>
                <div class="provider-stats">
                    ${d.total_hexes.toLocaleString()} hexes &middot;
                    ${d.total_locations.toLocaleString()} locations
                </div>
                <div class="provider-tech">${techInfo}</div>
                <div class="provider-actions">
                    <label class="toggle-label">
                        <input type="checkbox" ${p.visible ? "checked" : ""}
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
    const entry = providerLayers[id];
    entry.visible = visible;
    if (visible) {
        entry.layer.addTo(map);
    } else {
        map.removeLayer(entry.layer);
    }
}

function removeProvider(id) {
    const entry = providerLayers[id];
    if (entry) {
        map.removeLayer(entry.layer);
        delete providerLayers[id];
    }
    // Also delete from server
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
