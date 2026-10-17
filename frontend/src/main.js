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
        <span class="orbit-drop">💧</span>
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

    <section class="panel dashboard-panel" aria-labelledby="dashboard-title">
      <div class="panel-heading">
        <div>
          <p class="section-label">Society dashboard</p>
          <h2 id="dashboard-title">Assets needing attention</h2>
        </div>
        <span id="asset-count" class="panel-number">00</span>
      </div>
      <p class="panel-intro">Live asset records from the connected RainGuard API. Rainfall outlook is unavailable because no weather source is configured.</p>
      <div id="dashboard-status" class="form-status loading" role="status">Loading assets…</div>
      <div id="asset-list" class="asset-list" hidden></div>
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
          <span class="empty-icon" aria-hidden="true">◯</span>
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
const dashboardStatus = document.querySelector("#dashboard-status");
const assetList = document.querySelector("#asset-list");
const assetCount = document.querySelector("#asset-count");
let selectedAssetId = null;
let inspectionInProgress = false;
let lookupRequestId = 0;
let activeLookupController = null;
const missionsById = new Map();
const tasksByFindingId = new Map();
let maintenanceTasks = [];

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

function renderMission(mission) {
  const findingOptions = mission.checklist
    .map(
      (item) =>
        `<option value="${escapeHtml(item.id)}">${escapeHtml(item.prompt)}</option>`
    )
    .join("");
  const findings = mission.findings
    .map((finding) => {
      const task = tasksByFindingId.get(finding.id);
      const action = task
        ? `<span class="status-badge status-${escapeHtml(task.status)}">Task ${escapeHtml(task.status)}</span>`
        : finding.approved
          ? `<button type="button" class="secondary-button compact-button create-task-button" data-finding-id="${escapeHtml(finding.id)}" data-description="${escapeHtml(finding.description)}">Create task</button>`
        : `<button type="button" class="secondary-button compact-button approve-finding-button" data-finding-id="${escapeHtml(finding.id)}">Approve finding</button>`;
      return `<li><strong>${escapeHtml(finding.description)}</strong><span>${finding.approved ? "Human-approved" : "Awaiting human approval"}</span>${action}</li>`;
    })
    .join("");
  return `
    <div class="mission-card" data-mission-id="${escapeHtml(mission.id)}">
      <div class="incident-heading"><h4>Inspection mission</h4><span>${escapeHtml(mission.status)}</span></div>
      <form class="checklist-form">
        <ol class="checklist">${mission.checklist.map((item) => `
          <li>
            <label><input type="checkbox" name="completed" value="${escapeHtml(item.id)}" ${item.completed ? "checked" : ""} /> ${escapeHtml(item.prompt)}</label>
            <input name="response-${escapeHtml(item.id)}" value="${escapeHtml(item.response || "")}" maxlength="1000" placeholder="Field note (optional)" />
          </li>
        `).join("")}</ol>
        <label>Mission notes <textarea name="notes" rows="2" maxlength="3000">${escapeHtml(mission.notes || "")}</textarea></label>
        <button type="submit" class="primary-button compact-button">Save checklist</button>
      </form>
      <form class="finding-form">
        <label>Record an inspection finding
          <select name="checklist_item_id" required>${findingOptions}</select>
          <textarea name="description" rows="2" required placeholder="Field inspection observations"></textarea>
        </label>
        <button type="submit" class="primary-button compact-button">Save finding</button>
      </form>
      ${findings ? `<h4>Findings</h4><ul class="finding-list">${findings}</ul>` : ""}
    </div>
  `;
}

function renderMaintenance(tasks) {
  return `
    <div class="maintenance-section">
      <div class="incident-heading"><h3>Maintenance tasks</h3><span>${tasks.length} recorded</span></div>
      ${
        tasks.length
          ? `<ul class="task-list">${tasks.map((task) => {
              const nextStatus = task.status === "pending" ? "in_progress" : "completed";
              const label = task.status === "completed" ? "Completed" : `Mark ${nextStatus === "in_progress" ? "in progress" : "completed"}`;
              const completionForm = task.status !== "in_progress"
                ? ""
                : `<form class="task-update-form" data-task-id="${escapeHtml(task.id)}"><input name="completion_notes" placeholder="Completion notes" maxlength="3000" /><input name="evidence_refs" placeholder="Evidence reference (optional)" maxlength="500" /><button type="submit" class="secondary-button compact-button">Save completion</button></form>`;
              const dueInputValue = task.reinspection_due_at
                ? toDateTimeLocalValue(task.reinspection_due_at)
                : "";
              const reinspectionLabel = task.reinspection_status === "scheduled"
                ? task.reinspection_due_at
                  ? `Reinspection scheduled for ${escapeHtml(formatDateTime(task.reinspection_due_at))}`
                  : "Reinspection scheduled"
                : "Reinspection not scheduled";
              const reinspectionButton = `<div class="reinspection-controls">
                <small>${reinspectionLabel}</small>
                <label>${task.reinspection_status === "scheduled" ? "Change due date and time" : "Optional due date and time"}<input type="datetime-local" class="reinspection-due-input" value="${escapeHtml(dueInputValue)}" /></label>
                <button type="button" class="secondary-button compact-button reinspection-button" data-task-id="${escapeHtml(task.id)}" data-default-label="${task.reinspection_status === "scheduled" ? "Reschedule reinspection" : "Schedule reinspection"}">${task.reinspection_status === "scheduled" ? "Reschedule reinspection" : "Schedule reinspection"}</button>
              </div>`;
              const taskAction = task.status === "completed"
                ? `<span class="status-badge status-completed">Task completed</span>`
                : `<button type="button" class="secondary-button compact-button task-status-button" data-task-id="${escapeHtml(task.id)}" data-next-status="${nextStatus}">${label}</button>`;
              return `<li><strong>${escapeHtml(task.description)}</strong><span>${escapeHtml(task.priority)} · ${escapeHtml(task.status)}</span>${taskAction}${completionForm}${reinspectionButton}</li>`;
            }).join("")}</ul>`
          : `<div class="history-empty">No maintenance tasks recorded for this asset.</div>`
      }

    </div>
  `;
}

function renderMaintenanceState() {
  const maintenanceSection = assetResult.querySelector(".maintenance-section");
  if (maintenanceSection) {
    maintenanceSection.outerHTML = renderMaintenance(maintenanceTasks);
  }
  const missionArea = assetResult.querySelector(".mission-area");
  if (missionArea) {
    missionArea.innerHTML = Array.from(missionsById.values())
      .map(renderMission)
      .join("");
  }
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

function renderAssetList(assets) {
  assetCount.textContent = String(assets.length).padStart(2, "0");
  assetList.hidden = false;
  assetList.innerHTML = assets.length
    ? assets.map((asset) => `
      <button type="button" class="asset-list-item" data-asset-id="${escapeHtml(asset.id)}">
        <strong>${escapeHtml(asset.name)}</strong>
        <span>${escapeHtml(asset.location || "Location not specified")} · ${escapeHtml(asset.society_id)}</span>
      </button>
    `).join("")
    : `<div class="history-empty">No assets are registered yet.</div>`;
}

async function loadDashboard() {
  try {
    const assets = await requestJson("/assets");
    renderAssetList(assets);
    dashboardStatus.className = "form-status success";
    dashboardStatus.textContent = `${assets.length} asset${assets.length === 1 ? "" : "s"} available`;
  } catch (error) {
    dashboardStatus.className = "form-status error";
    dashboardStatus.textContent = error.message;
  }
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

function renderAsset(asset, incidents, inspections, risk, tasks, missions) {
  maintenanceTasks = tasks;
  tasksByFindingId.clear();
  tasks.forEach((task) => tasksByFindingId.set(task.finding_id, task));
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
    <div class="maintenance-workflow">
      <div class="incident-heading"><h3>Inspection to maintenance</h3></div>
      <p class="muted">Generate a checklist, record human findings, and approve only confirmed work.</p>
      <button type="button" class="secondary-button mission-button">Generate inspection mission</button>
      <div class="mission-area">${missions.length ? missions.map(renderMission).join("") : ""}</div>
    </div>
    ${renderMaintenance(tasks)}
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

function formatDateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "date unavailable"
    : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function toDateTimeLocalValue(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function parseDateTimeLocalValue(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) return null;
  const [, year, month, day, hours, minutes] = match.map(Number);
  const date = new Date(year, month - 1, day, hours, minutes);
  return date.getFullYear() === year
    && date.getMonth() === month - 1
    && date.getDate() === day
    && date.getHours() === hours
    && date.getMinutes() === minutes
    ? date
    : null;
}

assetResult.addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  const missionCard = button.closest(".mission-card");
  try {
    if (button.classList.contains("mission-button")) {
      const mission = await requestJson(
        `/assets/${encodeURIComponent(selectedAssetId)}/inspection-missions`,
        { method: "POST" }
      );
      missionsById.set(mission.id, mission);
      assetResult.querySelector(".mission-area").innerHTML = Array.from(missionsById.values()).map(renderMission).join("");
      return;
    }
    if (button.classList.contains("approve-finding-button")) {
      const mission = await requestJson(
        `/inspection-missions/${encodeURIComponent(missionCard.dataset.missionId)}/findings/${encodeURIComponent(button.dataset.findingId)}/approve`,
        { method: "POST" }
      );
      missionsById.set(mission.id, mission);
      assetResult.querySelector(".mission-area").innerHTML = Array.from(missionsById.values()).map(renderMission).join("");
      return;
    }
    if (button.classList.contains("create-task-button")) {
      if (button.disabled) return;
      button.disabled = true;
      try {
        const task = await requestJson("/maintenance-tasks", {
          method: "POST",
          body: JSON.stringify({
            asset_id: selectedAssetId,
            mission_id: missionCard.dataset.missionId,
            finding_id: button.dataset.findingId,
            description: button.dataset.description,
            priority: "medium",
          }),
        });
        maintenanceTasks = [
          ...maintenanceTasks.filter(
            (existing) => existing.finding_id !== task.finding_id
          ),
          task,
        ];
        tasksByFindingId.set(task.finding_id, task);
        renderMaintenanceState();
        setInspectionStatus("success", "Maintenance task created.");
      } catch (error) {
        button.disabled = false;
        throw error;
      }
      return;
    }
    if (button.classList.contains("task-status-button") && button.dataset.nextStatus) {
      const task = await requestJson(
        `/maintenance-tasks/${encodeURIComponent(button.dataset.taskId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: button.dataset.nextStatus }),
        }
      );
      button.textContent = task.status === "completed" ? "Completed" : `Mark ${task.status === "pending" ? "in progress" : "completed"}`;
      button.dataset.nextStatus = task.status === "completed" ? "" : "completed";
      return;
    }
    if (button.classList.contains("reinspection-button")) {
      if (button.disabled) return;
      const dueInput = button.closest(".reinspection-controls")?.querySelector(".reinspection-due-input");
      const dueValue = dueInput?.value;
      button.disabled = true;
      button.textContent = "Scheduling…";
      let task;
      try {
        const dueDate = dueValue ? parseDateTimeLocalValue(dueValue) : null;
        if (dueValue && !dueDate) {
          throw new Error("Enter a valid reinspection date and time.");
        }
        task = await requestJson(
          `/maintenance-tasks/${encodeURIComponent(button.dataset.taskId)}/reinspection`,
          {
            method: "POST",
            body: JSON.stringify({
              notes: "Follow-up verification requested by the maintenance team.",
              ...(dueDate ? { reinspection_due_at: dueDate.toISOString() } : {}),
            }),
          }
        );
      } catch (error) {
        button.disabled = false;
        button.textContent = button.dataset.defaultLabel;
        throw error;
      }
      maintenanceTasks = maintenanceTasks.map((existing) =>
        existing.id === task.id ? task : existing
      );
      renderMaintenanceState();
      setInspectionStatus("success", "Reinspection scheduled.");
    }
  } catch (error) {
    setInspectionStatus("error", error.message);
  }
});

assetResult.addEventListener("submit", async (event) => {
  if (event.target.classList.contains("task-update-form")) {
    event.preventDefault();
    const form = event.target;
    const values = Object.fromEntries(new FormData(form).entries());
    const evidence = values.evidence_refs ? [values.evidence_refs] : [];
    try {
      await requestJson(
        `/maintenance-tasks/${encodeURIComponent(form.dataset.taskId)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            status: "completed",
            completion_notes: values.completion_notes || null,
            evidence_refs: evidence,
          }),
        }
      );
      form.innerHTML = "<span>Completion saved.</span>";
    } catch (error) {
      setInspectionStatus("error", error.message);
    }
    return;
  }
  if (event.target.classList.contains("checklist-form")) {
    event.preventDefault();
    const form = event.target;
    const missionCard = form.closest(".mission-card");
    const mission = missionsById.get(missionCard.dataset.missionId);
    if (!mission) return;
    const formData = new FormData(form);
    const completed = new Set(formData.getAll("completed"));
    const checklist = mission.checklist.map((item) => ({
      ...item,
      completed: completed.has(item.id),
      response: formData.get(`response-${item.id}`) || null,
    }));
    try {
      const updatedMission = await requestJson(
        `/inspection-missions/${encodeURIComponent(mission.id)}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            checklist,
            notes: formData.get("notes") || null,
          }),
        }
      );
      missionsById.set(updatedMission.id, updatedMission);
      assetResult.querySelector(".mission-area").innerHTML = Array.from(missionsById.values()).map(renderMission).join("");
    } catch (error) {
      setInspectionStatus("error", error.message);
    }
    return;
  }
  if (!event.target.classList.contains("finding-form")) return;
  event.preventDefault();
  const form = event.target;
  const missionCard = form.closest(".mission-card");
  const payload = Object.fromEntries(new FormData(form).entries());
  try {
    const mission = await requestJson(
      `/inspection-missions/${encodeURIComponent(missionCard.dataset.missionId)}/findings`,
      { method: "POST", body: JSON.stringify(payload) }
    );
    missionsById.set(mission.id, mission);
    assetResult.querySelector(".mission-area").innerHTML = Array.from(missionsById.values()).map(renderMission).join("");
  } catch (error) {
    setInspectionStatus("error", error.message);
  }
});

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
    loadDashboard();
  } catch (error) {
    setFormStatus("error", error.message);
  } finally {
    button.disabled = false;
  }
});

assetList.addEventListener("click", (event) => {
  const button = event.target.closest("[data-asset-id]");
  if (!button) return;
  document.querySelector("#asset-id").value = button.dataset.assetId;
  lookupForm.requestSubmit();
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
    const tasks = await requestJson(
      `/assets/${encodeURIComponent(assetId)}/maintenance-tasks`,
      requestOptions
    );
    if (requestId !== lookupRequestId) return;
    const missions = await requestJson(
      `/assets/${encodeURIComponent(assetId)}/inspection-missions`,
      requestOptions
    );
    if (requestId !== lookupRequestId) return;
    missionsById.clear();
    missions.forEach((mission) => missionsById.set(mission.id, mission));
    renderAsset(asset, incidents, inspections, risk, tasks, missions);
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
loadDashboard();
