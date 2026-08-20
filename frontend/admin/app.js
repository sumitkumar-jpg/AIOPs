// Admin / Operations panel.
//
// Simulation-only surface: scenario/error injection, missing/stale source
// simulation and live telemetry. Incident diagnosis + human approval/execution
// live on the Dashboard.

const API = (window.AIOPS_API_BASE || "");
const POLL_MS = 3000;

const $ = (id) => document.getElementById(id);

let config = null;
let selectedScenario = null;
let injectInFlight = false;

let lastAuditId = null;

async function fetchJSON(path, options) {
  const res = await fetch(API + path, {
    headers: { "Accept": "application/json", ...(options && options.body ? { "Content-Type": "application/json" } : {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error("HTTP " + res.status + (text ? " - " + text.slice(0, 160) : ""));
  }
  return res.json();
}

function statusClass(s) {
  const v = (s || "").toLowerCase();
  if (["ok", "healthy", "up", "normal", "resolved", "executed", "low"].includes(v)) return "ok";
  if (["warn", "degraded", "recovering", "analyzed"].includes(v)) return "warn";
  if (["crit", "critical", "offline", "detected", "awaiting_approval", "medium", "high", "rejected"].includes(v)) return "crit";
  return "";
}

function setLive(id, value) {
  const el = $(id);
  if (!el) return;
  el.textContent = value;
  el.className = "v " + statusClass(value);
}

function fmtTime(iso) {
  if (!iso) return "--";
  return iso.replace("Z", "").replace("T", " ").slice(0, 19);
}

// --------------------------------------------------------------------------- //
// Config / scenario injection UI
// --------------------------------------------------------------------------- //
function renderScenarioList() {
  const list = $("scenario-list");
  list.innerHTML = "";
  config.scenarios.forEach(sc => {
    const item = document.createElement("div");
    item.className = "scenario-item" + (sc.id === selectedScenario ? " selected" : "");
    item.dataset.id = sc.id;
    item.innerHTML = `
      <div class="s-name">${sc.name}</div>
      <div class="s-meta">
        <span class="sev-badge ${sc.severity}">${sc.severity}</span>
        <span class="sev-badge low">${sc.root_cause_id}</span>
      </div>`;
    item.addEventListener("click", () => {
      selectedScenario = sc.id;
      document.querySelectorAll(".scenario-item").forEach(el => el.classList.toggle("selected", el.dataset.id === sc.id));
      $("inject-btn").disabled = !selectedScenario;
    });
    list.appendChild(item);
  });
}

function renderMissingSources() {
  const wrap = $("missing-sources");
  wrap.className = "check-list";
  wrap.innerHTML = "";
  Object.entries(config.telemetry_sources).forEach(([key, label]) => {
    const labelEl = document.createElement("label");
    labelEl.className = "check-item";
    labelEl.innerHTML = `<input type="checkbox" value="${key}" /> ${label}`;
    wrap.appendChild(labelEl);
  });
}

function selectedMissingSources() {
  return Array.from(document.querySelectorAll('#missing-sources input[type="checkbox"]:checked')).map(c => c.value);
}

async function injectScenario() {
  if (!selectedScenario || injectInFlight) return;
  injectInFlight = true;
  const btn = $("inject-btn");
  btn.disabled = true;
  const status = $("inject-status");
  status.textContent = "Injecting...";
  status.className = "inject-status";
  try {
    const missing = selectedMissingSources();
    const res = await fetchJSON("/api/scenarios/inject", {
      method: "POST",
      body: JSON.stringify({ scenario_id: selectedScenario, missing_sources: missing, stale_sources: missing }),
    });
    status.textContent = `Injected #${res.incident.id} — degraded telemetry is live.`;
    status.className = "inject-status ok";
    await refresh();
  } catch (err) {
    status.textContent = "Inject failed: " + err.message;
    status.className = "inject-status err";
  } finally {
    injectInFlight = false;
    btn.disabled = !selectedScenario;
  }
}

async function clearScenario() {
  const status = $("inject-status");
  status.textContent = "Clearing active scenario...";
  status.className = "inject-status";
  try {
    await fetchJSON("/api/scenarios/clear", { method: "POST", body: "{}" });
    status.textContent = "Scenario cleared. Telemetry back to NORMAL.";
    status.className = "inject-status ok";
    await refresh();
  } catch (err) {
    status.textContent = "Clear failed: " + err.message;
    status.className = "inject-status err";
  }
}

// --------------------------------------------------------------------------- //
// Live telemetry strip
// --------------------------------------------------------------------------- //
function renderLiveTelemetry(tel) {
  const stateEl = $("live-state");
  stateEl.textContent = tel.state;
  stateEl.className = "v " + (tel.state === "NORMAL" ? "ok" : tel.state === "DEGRADED" ? "crit" : "warn");
  $("live-scenario").textContent = tel.active_scenario ? tel.active_scenario.name : "none";

  setLive("live-network", (tel.sources.network || {}).status || "--");
  setLive("live-app", (tel.sources.application || {}).status || "--");
  setLive("live-facility", (tel.sources.facility || {}).status || "--");
  setLive("live-iot", (tel.sources.iot || {}).status || "--");

  const missing = (tel.missing_sources || []).concat(
    (tel.stale_sources || []).map(s => (typeof s === "string" ? s + " (stale)" : s.source + " (stale)"))
  );
  const missEl = $("live-missing");
  missEl.textContent = missing.length ? missing.join(", ") : "none";
  missEl.className = "v " + (missing.length ? "crit" : "ok");
}

// --------------------------------------------------------------------------- //
// Audit trail (append-only)
// --------------------------------------------------------------------------- //
function auditRows(items) {
  return items.map(a => `
    <tr data-audit-id="${a.id}">
      <td>${fmtTime(a.timestamp)}</td>
      <td>${a.actor}</td>
      <td>${a.action}</td>
      <td class="detail-cell">${a.detail}</td>
      <td>${a.incident_id ? "#" + a.incident_id : "--"}</td>
    </tr>`).join("");
}

function renderAudit(entries) {
  const body = $("audit-body");
  if (!entries.length) {
    body.innerHTML = `<tr><td colspan="5" class="muted">No audit entries yet.</td></tr>`;
    lastAuditId = null;
    return;
  }
  const newestId = entries[0].id;
  if (lastAuditId == null) {
    body.innerHTML = auditRows(entries);
  } else {
    const fresh = entries.filter(a => a.id > lastAuditId);
    if (fresh.length) {
      body.insertAdjacentHTML("afterbegin", auditRows(fresh));
    }
  }
  lastAuditId = newestId;
}

// --------------------------------------------------------------------------- //
// Polling
// --------------------------------------------------------------------------- //
async function refresh() {
  try {
    const [tel, audit] = await Promise.all([
      fetchJSON("/api/telemetry/current"),
      fetchJSON("/api/audit"),
    ]);

    renderLiveTelemetry(tel);
    renderAudit(audit);

    $("conn-badge").textContent = "connected";
    $("conn-badge").className = "conn-badge ok";
  } catch (err) {
    $("conn-badge").textContent = "offline";
    $("conn-badge").className = "conn-badge err";
  }
}

// --------------------------------------------------------------------------- //
// Init
// --------------------------------------------------------------------------- //
(async function init() {
  try {
    config = await fetchJSON("/api/config");
    selectedScenario = config.scenarios[0] ? config.scenarios[0].id : null;
    renderScenarioList();
    renderMissingSources();
    $("inject-btn").disabled = !selectedScenario;
    $("inject-btn").addEventListener("click", injectScenario);
    $("clear-btn").addEventListener("click", clearScenario);
    await refresh();
    setInterval(refresh, POLL_MS);
  } catch (err) {
    $("conn-badge").textContent = "offline";
    $("conn-badge").className = "conn-badge err";
    const status = $("inject-status");
    if (status) {
      status.textContent = "Cannot reach API: " + err.message;
      status.className = "inject-status err";
    }
  }
})();
