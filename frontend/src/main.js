import "./style.css";

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const app = document.querySelector("#app");

app.innerHTML = `
  <section class="card">
    <p class="eyebrow">RainGuard AI</p>
    <h1>Go Outside Before the Rain Does</h1>
    <p class="description">Preventive maintenance starts with a working connection to the RainGuard API.</p>
    <p id="health-status" class="status" role="status">Checking backend connection…</p>
    <p id="health-details" class="details"></p>
  </section>
`;

const status = document.querySelector("#health-status");
const details = document.querySelector("#health-details");

async function checkBackendHealth() {
  try {
    const response = await fetch(`${apiBaseUrl}/health`);
    if (!response.ok) {
      throw new Error(`Backend returned HTTP ${response.status}`);
    }

    const health = await response.json();
    if (health.status !== "ok" || health.service !== "rainguard-api") {
      throw new Error("Backend returned an unexpected health response");
    }

    status.textContent = "Backend connection succeeded.";
    status.className = "status success";
    details.textContent = `${health.service} is healthy at ${apiBaseUrl}/health`;
  } catch (error) {
    status.textContent = "Backend connection failed.";
    status.className = "status error";
    details.textContent = error instanceof Error ? error.message : "Unknown connection error";
  }
}

checkBackendHealth();
