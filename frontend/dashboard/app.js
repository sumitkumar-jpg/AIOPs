// Dashboard: reads telemetry + incidents via fetch() and updates the DOM in
// place. Never reloads the page; polling replaces only changed values.

const API = (window.AIOPS_API_BASE || "");
const POLL_MS = 5000;

const $ = (id) => document.getElementById(id);

// Execution note for the active incident. The textarea is a static DOM node
// (never rebuilt), so its value and focus survive all background updates.
const pendingNotes = {};

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
  if (["crit", "critical", "offline", "detected", "awaiting_approval", "medium", "high"].includes(v)) return "crit";
  return "";
}

function setBadge(el, text) {
  if (!el) return;
  el.textContent = text || "--";
  el.classList.remove("ok", "warn", "crit");
  const color = statusClass(text);
  if (color) el.classList.add(color);
}

function fmt(n) {
  if (n === null || n === undefined) return "--";
  return typeof n === "number" ? n.toLocaleString() : n;
}

// --------------------------------------------------------------------------- //
// Display name maps (cosmetic only — backend identifiers stay unchanged)
// --------------------------------------------------------------------------- //
const DEVICE_DISPLAY = {
  "dc01-core-sw01": "CORE-SW01",
  "dc01-core-sw02": "CORE-SW02",
  "dc01-edge-rtr01": "EDGE-RTR01",
  "dc01-edge-rtr02": "EDGE-RTR02",
};

const SERVICE_DISPLAY = {
  "api-gateway": "API Gateway",
  "auth-service": "Auth Service",
  "checkout-service": "Checkout Service",
  "orders-service": "Orders Service",
  "search-service": "Search Service",
  "payments-service": "Payments Service",
};

const SENSOR_DISPLAY = {
  "dc01-rack-a01-inlet-temp": { label: "Rack A01 — Inlet", unit: "°C" },
  "dc01-rack-a02-inlet-temp": { label: "Rack A02 — Inlet", unit: "°C" },
  "dc01-hall-temp": { label: "Hall Temp", unit: "°C" },
  "dc01-hall-humidity": { label: "Hall Humidity", unit: "%" },
  "dc01-water-leak": { label: "Water Leak", unit: null, boolMode: true },
  "hvac-a-fan-rpm": { label: "HVAC-A Fan", unit: "RPM" },
  "dc01-ups-load": { label: "UPS Load", unit: "%" },
};

function deviceName(id) {
  return DEVICE_DISPLAY[id] || id;
}

function serviceName(id) {
  return SERVICE_DISPLAY[id] || id;
}

function sensorInfo(id) {
  return SENSOR_DISPLAY[id] || { label: id, unit: null };
}

function formatSensorValue(value, info) {
  if (value === null || value === undefined) return "--";
  if (info.boolMode) {
    return value === 0 || value === false ? "CLEAR" : "DETECTED";
  }
  const num = typeof value === "number" ? value.toLocaleString() : value;
  return info.unit ? num + " " + info.unit : num;
}

// --------------------------------------------------------------------------- //
// Telemetry
// --------------------------------------------------------------------------- //
function renderHealth(tel) {
  const pill = $("health-pill");
  const state = tel.state || "NORMAL";
  pill.classList.remove("normal", "degraded", "critical", "recovering");
  pill.classList.add(state.toLowerCase());
  $("health-label").textContent = state;
  $("active-scenario").textContent = tel.active_scenario
    ? "Scenario: " + tel.active_scenario.name
    : "No active scenario";
  $("last-updated").textContent = "updated " + new Date().toLocaleTimeString();
}

function renderNetwork(net) {
  setBadge($("net-status"), net.status);
  $("net-throughput").textContent = net.throughput_mbps != null
    ? fmt(net.throughput_mbps) + " Mbps" : "-- Mbps";
  const body = $("net-devices");
  if (net.status === "OFFLINE" && body.dataset.offline === "1") return;
  let html = "";
  for (const d of net.devices || []) {
    html += `<tr>
      <td>${deviceName(d.name)}</td>
      <td><span class="status-badge ${statusClass(d.status)}">${d.status || "--"}</span></td>
      <td>${fmt(d.latency_ms)}${d.latency_ms != null ? " ms" : ""}</td>
      <td>${fmt(d.loss_pct)}${d.loss_pct != null ? " %" : ""}</td>
    </tr>`;
  }
  body.innerHTML = html;
  body.dataset.offline = net.status === "OFFLINE" ? "1" : "0";
}

function renderApplication(app) {
  setBadge($("app-status"), app.status);
  const q = app.queue || {};
  $("q-depth").textContent = fmt(q.depth);
  $("q-lag").textContent = fmt(q.lag);
  $("q-consumers").textContent = fmt(q.consumers);
  let html = "";
  for (const s of app.services || []) {
    html += `<tr>
      <td>${serviceName(s.name)}</td>
      <td><span class="status-badge ${statusClass(s.status)}">${s.status || "--"}</span></td>
      <td>${fmt(s.response_time_ms)}${s.response_time_ms != null ? " ms" : ""}</td>
      <td>${fmt(s.error_rate_pct)}${s.error_rate_pct != null ? " %" : ""}</td>
    </tr>`;
  }
  $("app-services").innerHTML = html;
}

function renderFacility(fac) {
  setBadge($("fac-status"), fac.status);
  const tempCls = fac.temperature_c >= 30 ? "hot" : fac.temperature_c >= 27 ? "warm" : "";
  const battCls = fac.ups_battery_pct != null && fac.ups_battery_pct < 40 ? "hot" : "";
  const upsCls = fac.ups_status === "ONLINE" ? "ok" : fac.ups_status === "ON_BATTERY" ? "hot" : "";
  const hvacCls = fac.hvac_status === "RUNNING" ? "ok" : fac.hvac_status === "FAULT" ? "hot" : "";
  $("fac-metrics").innerHTML = `
    <div class="metric"><div class="m-label">Room Temperature</div><div class="m-value ${tempCls}">${fmt(fac.temperature_c)} °C</div></div>
    <div class="metric"><div class="m-label">Humidity</div><div class="m-value">${fmt(fac.humidity_pct)} %</div></div>
    <div class="metric"><div class="m-label">Power Load</div><div class="m-value">${fmt(fac.power_load_kw)} kW</div></div>
    <div class="metric"><div class="m-label">UPS Status</div><div class="m-value ${upsCls}">${fac.ups_status || "--"}</div></div>
    <div class="metric"><div class="m-label">Battery</div><div class="m-value ${battCls}">${fmt(fac.ups_battery_pct)} %</div></div>
    <div class="metric"><div class="m-label">HVAC</div><div class="m-value ${hvacCls}">${fac.hvac_status || "--"}</div></div>
  `;
  const alarms = fac.alarms || [];
  $("fac-alarms").innerHTML = alarms.length
    ? alarms.map(a => `<div class="alarm">▲ ${a.name} <span class="alarm-sev">(${a.severity})</span></div>`).join("")
    : "";
}

function renderIot(iot) {
  setBadge($("iot-status"), iot.status);
  let html = "";
  for (const s of iot.sensors || []) {
    const cls = s.status === "OFFLINE" ? "off" : (s.status === "CRITICAL" ? "crit" : (s.status === "FLAKY" ? "warn" : "ok"));
    const info = sensorInfo(s.name);
    html += `<div class="sensor ${cls}"><span class="s-name">${info.label}</span><span class="s-val">${formatSensorValue(s.value, info)}</span></div>`;
  }
  $("iot-sensors").innerHTML = html;
}

// --------------------------------------------------------------------------- //
// Incidents + diagnosis
// --------------------------------------------------------------------------- //
function renderDiagnosis(incident) {
  if (!incident) {
    $("diagnosis-body").classList.add("hidden");
    $("diagnosis-empty").classList.remove("hidden");
    return;
  }
  $("diagnosis-empty").classList.add("hidden");
  $("diagnosis-body").classList.remove("hidden");
  const d = incident.diagnosis || {};
  setBadge($("diag-incident-status"), incident.status);
  $("diag-incident-id").textContent = `incident #${incident.id} · ${incident.scenario_name}`;
  $("diag-root-cause").textContent = d.likely_root_cause || "--";
  $("diag-confidence").textContent = d.confidence != null ? Math.round(d.confidence * 100) + "%" : "--";
  const riskEl = $("diag-risk");
  riskEl.textContent = d.risk_level || "--";
  riskEl.className = "status-badge " + (d.risk_level === "HIGH" ? "crit" : d.risk_level === "MEDIUM" ? "crit" : "ok");
  const pb = d.recommended_playbook_id || "--";
  $("diag-playbook").textContent = pb;
  $("diag-missing").textContent = (d.missing_data_sources && d.missing_data_sources.length)
    ? d.missing_data_sources.join(", ") : "none";
  $("diag-engine").textContent = (d.ai_engine === "groq" ? "Groq · " + d.ai_engine : d.ai_engine) + (d.ai_note ? " — " + d.ai_note : "");
  $("diag-reasoning").textContent = d.reasoning || "";

  const panel = $("approval-panel");
  const resultEl = $("exec-result");
  const statusEl = $("approve-status");
  const noteEl = $("exec-note");

  // Re-point the (static) textarea at this incident, preserving any typed note.
  if (pendingNotes[incident.id] != null && noteEl.value !== pendingNotes[incident.id]) {
    noteEl.value = pendingNotes[incident.id];
  } else {
    pendingNotes[incident.id] = noteEl.value;
  }

  if (incident.status === "AWAITING_APPROVAL") {
    panel.classList.remove("hidden");
    resultEl.classList.add("hidden");
    $("approve-btn").disabled = false;
  } else {
    panel.classList.add("hidden");
    if (statusEl) statusEl.textContent = "";
    const decision = incident.decision || {};
    if (decision.status === "EXECUTED" && decision.result) {
      const r = decision.result;
      resultEl.classList.remove("hidden");
      resultEl.innerHTML = `Playbook <b>${decision.playbook_title}</b> (${decision.risk_level} risk) executed${
        decision.executed_at ? " at " + decision.executed_at.replace("Z", "").replace("T", " ").slice(0, 19) : ""}.<br>
        <b>${r.result}</b>${r.steps_executed && r.steps_executed.length
          ? `<ul class="step-list">${r.steps_executed.map(s => `<li>${s}</li>`).join("")}</ul>` : ""}`;
    } else {
      resultEl.classList.add("hidden");
    }
  }
}

async function approveExecution() {
  const btn = $("approve-btn");
  if (btn.disabled) return;
  btn.disabled = true;
  const statusEl = $("approve-status");
  statusEl.textContent = "Executing playbook...";
  statusEl.className = "inject-status";
  const incident = $("diag-incident-id").textContent;
  const note = $("exec-note").value;
  const match = incident.match(/#(\d+)/);
  const id = match ? Number(match[1]) : null;
  try {
    if (!id) throw new Error("unknown incident");
    await fetchJSON(`/api/incidents/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ note }),
    });
    pendingNotes[id] = "";
    statusEl.textContent = "Playbook executed.";
    statusEl.className = "inject-status ok";
    await refresh();
  } catch (err) {
    btn.disabled = false;
    statusEl.textContent = "Approval failed: " + err.message;
    statusEl.className = "inject-status err";
  }
}

function renderHistory(incidents) {
  const body = $("history-body");
  const rows = incidents.map(i => {
    const d = i.diagnosis || {};
    return `<tr>
      <td>#${i.id}</td>
      <td>${i.scenario_name}</td>
      <td><span class="status-badge ${statusClass(i.status)}">${i.status}</span></td>
      <td>${d.likely_root_cause || "--"}</td>
      <td>${d.risk_level || "--"}</td>
      <td>${d.recommended_playbook_id || "--"}</td>
      <td>${d.confidence != null ? Math.round(d.confidence * 100) + "%" : "--"}</td>
      <td>${(i.detected_at || "").replace("Z", "").replace("T", " ").slice(0, 19)}</td>
    </tr>`;
  });
  if (rows.length) {
    body.innerHTML = rows.join("");
  }
}

// --------------------------------------------------------------------------- //
// Polling
// --------------------------------------------------------------------------- //
async function refresh() {
  try {
    const [tel, incidents] = await Promise.all([
      fetchJSON("/api/telemetry/current"),
      fetchJSON("/api/incidents"),
    ]);
    renderHealth(tel);
    renderNetwork(tel.sources.network);
    renderApplication(tel.sources.application);
    renderFacility(tel.sources.facility);
    renderIot(tel.sources.iot);
    renderHistory(incidents);

    const active = incidents.find(i => ["DETECTED", "ANALYZED", "AWAITING_APPROVAL", "EXECUTED"].includes(i.status))
      || incidents[0] || null;
    renderDiagnosis(active);

    $("conn-badge").textContent = "connected";
    $("conn-badge").className = "conn-badge ok";
  } catch (err) {
    $("conn-badge").textContent = "offline";
    $("conn-badge").className = "conn-badge err";
  }
}

refresh();
setInterval(refresh, POLL_MS);
$("approve-btn").addEventListener("click", approveExecution);
$("exec-note").addEventListener("input", (e) => {
  const match = $("diag-incident-id").textContent.match(/#(\d+)/);
  const id = match ? Number(match[1]) : null;
  if (id != null) pendingNotes[id] = e.target.value;
});
