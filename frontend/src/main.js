import "./style.css";

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
).replace(/\/$/, "");
const app = document.querySelector("#app");

app.innerHTML = `
  <header class="topbar">
    <a class="brand" href="/">
      <span class="brand-mark" aria-hidden="true">RG</span>
      <span>RainGuard <strong>AI</strong></span>
    </a>
    <span class="badge">Preventive maintenance</span>
  </header>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">Go outside before the rain does</p>
        <h1>Know your building.<br /><em>Act before the weather.</em></h1>
        <p class="hero-copy">A clear view of the places that need attention, starting with the assets that keep your society moving.</p>
      </div>
      <div class="hero-orbit" aria-hidden="true">
        <span class="orbit-ring ring-one"></span>
        <span class="orbit-ring ring-two"></span>
        <span class="orbit-drop">⌁</span>
      </div>
    </section>

    <section class="connection-panel" aria-labelledby="connection-title">
      <div>
        <p class="section-label">System connection</p>
        <h2 id="connection-title">RainGuard API</h2>
      </div>
      <div class="connection-state">
        <span id="health-indicator" class="indicator loading"></span>
        <span id="health-status" role="status">Checking connection…</span>
        <span id="health-details" class="muted"></span>
      </div>
    </section>

    <div class="content-grid">
      <section class="panel" aria-labelledby="create-title">
        <div class="panel-heading">
          <div>
            <p class="section-label">Asset registry</p>
            <h2 id="create-title">Add an asset</h2>
          </div>
          <span class="panel-number">01</span>
        </div>
        <p class="panel-intro">Record a drain, pump, gate, or other place that deserves a closer look.</p>
        <form id="asset-form">
          <label>
            Society ID
            <input name="society_id" required maxlength="100" placeholder="e.g. society-1" />
          </label>
          <label>
            Asset name
            <input name="name" required maxlength="200" placeholder="e.g. North stormwater drain" />
          </label>
          <label>
            Location <span class="optional">Optional</span>
            <input name="location" maxlength="500" placeholder="e.g., Near Gate 2, Block A" />
          </label>
          <label>
            Description <span class="optional">Optional</span>
            <textarea name="description" maxlength="2000" rows="3" placeholder="e.g., Drain frequently gets blocked by leaves during heavy rain."></textarea>
          </label>
          <button type="submit" class="primary-button">
            <span>Create asset</span><span aria-hidden="true">→</span>
          </button>
          <p id="form-status" class="form-status" role="status"></p>
        </form>
      </section>

      <section class="panel lookup-panel" aria-labelledby="lookup-title">
        <div class="panel-heading">
          <div>
            <p class="section-label">Field view</p>
            <h2 id="lookup-title">Find an asset</h2>
          </div>
          <span class="panel-number">02</span>
        </div>
        <p class="panel-intro">Enter an asset ID to see its record and the incidents already observed there.</p>
        <form id="lookup-form" class="lookup-form">
          <label for="asset-id">Select an asset</label><p class="field-help">Find the asset ID in the asset record after creating an asset.</p>
          <div class="lookup-row">
            <input id="asset-id" name="asset_id" required placeholder="Enter the asset ID" />
            <button type="submit" class="secondary-button">Retrieve</button>
          </div>
        </form>
        <form id="inspection-form" class="inspection-form" hidden>
          <label for="inspection-image">Inspect a photo for this asset</label>
          <input id="inspection-image" name="file" type="file" accept="image/jpeg,image/png,image/webp" required />
          <span id="inspection-file-name" class="muted">JPEG, PNG, or WebP · maximum 5 MB</span>
          <button type="submit" class="secondary-button">Analyze photo</button>
          <p id="inspection-status" class="form-status" role="status"></p>
        </form>
        <div id="lookup-status" class="lookup-status empty-state">
          <span class="empty-icon" aria-hidden="true">◌</span>
          <strong>No asset selected</strong>
          <span>Retrieve an asset to view its maintenance history.</span>
        </div>
        <div id="asset-result" class="asset-result" hidden></div>
      </section>
    </div>
  </main>
  <footer>RainGuard AI <span>·</span> Built for earlier action, not emergency response.</footer>
`;

const healthStatus = document.querySelector("#health-status");
const healthDetails = document.querySelector("#health-details");
const healthIndicator = document.querySelector("#health-indicator");
const assetForm = document.querySelector("#asset-form");
const formStatus = document.querySelector("#form-status");
const lookupForm = document.querySelector("#lookup-form");
const lookupStatus = document.querySelector("#lookup-status");
const assetResult = document.querySelector("#asset-result");
const inspectionForm = document.querySelector("#inspection-form");
const inspectionImage = document.querySelector("#inspection-image");
const inspectionFileName = document.querySelector("#inspection-file-name");
const inspectionStatus = document.querySelector("#inspection-status");
let selectedAssetId = null;
let inspectionInProgress = false;
let lookupRequestId = 0;
let activeLookupController = null;

function setHealthState(state, message, details = "") {
  healthIndicator.className = `indicator ${state}`;
  healthStatus.textContent = message;
  healthDetails.textContent = details;
}

function renderRiskAssessment(risk) {
  return `
    <div class="risk-section">
      <div class="incident-heading">
        <h3>Maintenance priority</h3>
        <span class="risk-priority risk-${escapeHtml(risk.priority)}">${escapeHtml(risk.priority)}</span>
      </div>
      <p class="risk-score">Baseline score ${escapeHtml(risk.score)} · assessed ${formatDate(risk.assessed_at)}</p>
      <h4>Evidence</h4>
      <ul>${risk.evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      ${
        risk.data_quality_warnings.length
          ? `<h4>Data quality warnings</h4><ul class="risk-warnings">${risk.data_quality_warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
          : ""
      }
      <p class="human-review"><strong>Human review required.</strong> This provisional baseline is not an engineering standard or flood probability.</p>
    </div>
  `;
}

function setInspectionStatus(state, message) {
  inspectionStatus.className = `form-status ${state}`;
  inspectionStatus.textContent = message;
}

function setFormStatus(state, message) {
  formStatus.className = `form-status ${state}`;
  formStatus.textContent = message;
}

function renderInspection(inspection) {
  if (inspection.status === "failed") {
    return `<div class="inspection-result error"><strong>Photo analysis failed.</strong><span>Reference: ${escapeHtml(inspection.error_code || "provider error")}</span></div>`;
  }
  if (inspection.status === "pending") {
    return `<div class="inspection-result"><strong>Photo analysis is still processing.</strong><span>Please check this asset again shortly.</span></div>`;
  }
  const report = inspection.report;
  if (!report) {
    return `<div class="inspection-result error"><strong>Photo analysis is unavailable.</strong><span>Reference: ${escapeHtml(inspection.error_code || "provider error")}</span></div>`;
  }
  return `
    <div class="inspection-result">
      <div class="inspection-heading">
        <h3>Photo analysis</h3>
        <span class="severity-${escapeHtml(report.severity)}">${escapeHtml(report.severity)} severity</span>
      </div>
      <p>${escapeHtml(report.summary)}</p>
      <h4>Observations</h4>
      <ul>${report.observations.map((item) => `<li><strong>${escapeHtml(item.concern)}</strong> · ${escapeHtml(item.description)}</li>`).join("")}</ul>
      <h4>Recommended actions</h4>
      <ul>${report.recommended_actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>
      <p class="human-review"><strong>Human review required.</strong> This report is advisory and does not certify site safety.</p>
    </div>
  `;
}

function setLookupState(state, message, detail = "") {
  lookupStatus.className = `lookup-status ${state}`;
  lookupStatus.innerHTML = `<strong>${message}</strong>${detail ? `<span>${detail}</span>` : ""}`;
}

async function requestJson(path, options = {}) {
  let response;
  try {
    const requestOptions = { ...options };
    if (requestOptions.body && !(requestOptions.body instanceof FormData)) {
      requestOptions.headers = {
        "Content-Type": "application/json",
        ...requestOptions.headers,
      };
    }
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...requestOptions,
    });
  } catch {
    if (requestOptions.signal?.aborted) {
      throw new DOMException("Request aborted", "AbortError");
    }
    throw new Error("The backend could not be reached. Check that the API is running.");
  }

  if (!response.ok) {
    if (response.status === 404) throw new Error("Asset not found.");
    if (response.status === 400) throw new Error("That asset ID is not valid.");
    if (response.status === 413) throw new Error("The image exceeds the 5 MB limit.");
    if (response.status === 422) throw new Error("Please check the asset details and try again.");
    if (response.status === 429) throw new Error("Image analysis quota or rate limit was reached.");
    if (response.status === 503) throw new Error("The database is temporarily unavailable.");
    if (response.status === 502) throw new Error("Image analysis is temporarily unavailable.");
    throw new Error("The request could not be completed.");
  }

  return response.json();
}

async function checkBackendHealth() {
  setHealthState("loading", "Checking connection…");
  try {
    const health = await requestJson("/health");
    if (health.status !== "ok" || health.service !== "rainguard-api") {
      throw new Error("The backend returned an unexpected health response.");
    }
    setHealthState("success", "Connected", `${health.service} · ${apiBaseUrl}`);
  } catch (error) {
    setHealthState("error", "Connection unavailable", error.message);
  }
}

function renderAsset(asset, incidents, inspections, risk) {
  assetResult.hidden = false;
  assetResult.innerHTML = `
    <div class="asset-summary">
      <span class="asset-tag">Asset record</span>
      <h3>${escapeHtml(asset.name)}</h3>
      <p>${escapeHtml(asset.description || "No description provided.")}</p>
      <dl>
        <div><dt>Society</dt><dd>${escapeHtml(asset.society_id)}</dd></div>
        <div><dt>Location</dt><dd>${escapeHtml(asset.location || "Not specified")}</dd></div>
        <div><dt>ID</dt><dd class="id-value">${escapeHtml(asset.id)}</dd></div>
      </dl>
    </div>
    <div class="incident-section">
      <div class="incident-heading">
        <h3>Incident history</h3>
        <span>${incidents.length} recorded</span>
      </div>
      ${
        incidents.length
          ? `<ul class="incident-list">${incidents
              .map(
                (incident) => `
                  <li>
                    <span class="incident-dot" aria-hidden="true"></span>
                    <div><strong>${escapeHtml(incident.summary)}</strong><small>${formatDate(incident.occurred_at)}</small></div>
                  </li>`
              )
              .join("")}</ul>`
          : `<div class="history-empty">No incidents recorded for this asset.</div>`
      }
    </div>
    <div class="inspection-history">
      <div class="incident-heading">
        <h3>Photo inspections</h3>
        <span>${inspections.length} recorded</span>
      </div>
      ${
        inspections.length
          ? inspections.map((inspection) => renderInspection(inspection)).join("")
          : `<div class="history-empty">No photo inspections recorded for this asset.</div>`
      }
    </div>
    ${renderRiskAssessment(risk)}
  `;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  })[character]);
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : date.toLocaleDateString(undefined, { dateStyle: "medium" });
}

assetForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(assetForm);
  const payload = Object.fromEntries(formData.entries());
  Object.keys(payload).forEach((key) => {
    if (!payload[key]) delete payload[key];
  });

  setFormStatus("loading", "Saving asset…");
  const button = assetForm.querySelector("button");
  button.disabled = true;
  try {
    const asset = await requestJson("/assets", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setFormStatus("success", `Asset created · ${asset.id}`);
    assetForm.reset();
    document.querySelector("#asset-id").value = asset.id;
  } catch (error) {
    setFormStatus("error", error.message);
  } finally {
    button.disabled = false;
  }
});

inspectionImage.addEventListener("change", () => {
  const file = inspectionImage.files[0];
  inspectionFileName.textContent = file
    ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`
    : "JPEG, PNG, or WebP · maximum 5 MB";
});

inspectionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = inspectionImage.files[0];
  if (inspectionInProgress || !selectedAssetId || !file) return;

  inspectionInProgress = true;
  setInspectionStatus("loading", "Uploading photo and analyzing…");
  const button = inspectionForm.querySelector("button");
  button.disabled = true;
  try {
    const body = new FormData();
    body.append("file", file);
    const inspection = await requestJson(
      `/assets/${encodeURIComponent(selectedAssetId)}/inspections`,
      { method: "POST", body }
    );
    if (inspection.status !== "completed") {
      throw new Error("Image analysis did not complete.");
    }
    assetResult.insertAdjacentHTML("beforeend", renderInspection(inspection));
    setInspectionStatus("success", "Photo analyzed successfully.");
    inspectionForm.reset();
    inspectionFileName.textContent = "JPEG, PNG, or WebP · maximum 5 MB";
  } catch (error) {
    setInspectionStatus("error", error.message);
  } finally {
    inspectionInProgress = false;
    button.disabled = false;
  }
});

lookupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const assetId = new FormData(lookupForm).get("asset_id").trim();
  if (!assetId) return;

  activeLookupController?.abort();
  const requestId = ++lookupRequestId;
  const controller = new AbortController();
  activeLookupController = controller;
  assetResult.hidden = true;
  lookupStatus.hidden = false;
  setLookupState("loading", "Retrieving asset…");
  const button = lookupForm.querySelector("button");
  button.disabled = true;
  try {
    const requestOptions = { signal: controller.signal };
    const asset = await requestJson(
      `/assets/${encodeURIComponent(assetId)}`,
      requestOptions
    );
    if (requestId !== lookupRequestId) return;
    selectedAssetId = asset.id;
    const incidents = await requestJson(
      `/assets/${encodeURIComponent(assetId)}/incidents`,
      requestOptions
    );
    if (requestId !== lookupRequestId) return;
    const inspections = await requestJson(
      `/assets/${encodeURIComponent(assetId)}/inspections`,
      requestOptions
    );
    if (requestId !== lookupRequestId) return;
    const risk = await requestJson(
      `/assets/${encodeURIComponent(assetId)}/risk-assessments`,
      { method: "POST", signal: controller.signal }
    );
    if (requestId !== lookupRequestId) return;
    renderAsset(asset, incidents, inspections, risk);
    inspectionForm.hidden = false;
    setInspectionStatus("", "");
    lookupStatus.hidden = true;
  } catch (error) {
    if (requestId !== lookupRequestId || error.name === "AbortError") return;
    setLookupState("error", "Could not retrieve asset", error.message);
    lookupStatus.hidden = false;
  } finally {
    if (requestId === lookupRequestId) {
      button.disabled = false;
      activeLookupController = null;
      if (lookupStatus.classList.contains("loading")) {
        setLookupState(
          "empty",
          "No asset selected",
          "Retrieve an asset to view its maintenance history."
        );
      }
    }
  }
});

checkBackendHealth();
