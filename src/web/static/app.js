const stateBadge = document.getElementById("stateBadge");
const tierBadge = document.getElementById("tierBadge");
const statusLine = document.getElementById("statusLine");
const chatFeed = document.getElementById("chatFeed");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const workspaceInput = document.getElementById("workspaceInput");

const cpuVal = document.getElementById("cpuVal");
const cpuBar = document.getElementById("cpuBar");
const ramVal = document.getElementById("ramVal");
const ramBar = document.getElementById("ramBar");
const gpuVal = document.getElementById("gpuVal");
const gpuBar = document.getElementById("gpuBar");
const vramVal = document.getElementById("vramVal");
const vramBar = document.getElementById("vramBar");
const vramAlert = document.getElementById("vramAlert");

let atomState = "booting";
let online = true;
let audioLevel = 0.0;
let phase = 0.0;
let arcAngle = 0.0;

function updateState(newState) {
  atomState = newState;
  stateBadge.textContent = String(newState).toUpperCase();
}

function updateOnline(isOnline) {
  online = Boolean(isOnline);
  document.body.classList.toggle("offline-mode", !online);
}

function appendChat(entry) {
  const div = document.createElement("div");
  div.className = `chat-bubble ${entry.role === "user" ? "user" : "atom"}`;
  const meta = document.createElement("div");
  meta.className = "chat-meta";
  meta.innerHTML = `<span>${entry.role === "user" ? "YOU" : "A.T.O.M."}</span><span>${entry.tier || ""} ${entry.ts || ""}</span>`;
  const body = document.createElement("div");
  body.textContent = entry.text;
  div.appendChild(meta);
  div.appendChild(body);
  chatFeed.appendChild(div);
  chatFeed.scrollTop = chatFeed.scrollHeight;
}

function updateTelemetry(t, tier) {
  if (tier) tierBadge.textContent = tier;
  cpuVal.textContent = `${t.cpu_percent.toFixed(1)}%`;
  cpuBar.style.width = `${Math.min(100, t.cpu_percent)}%`;

  ramVal.textContent = `${t.ram_used_gb.toFixed(1)} / ${t.ram_total_gb.toFixed(1)} GB`;
  ramBar.style.width = `${Math.min(100, t.ram_percent)}%`;

  if (t.gpu_available) {
    gpuVal.textContent = `${t.gpu_percent.toFixed(1)}%`;
    gpuBar.style.width = `${Math.min(100, t.gpu_percent)}%`;
    const vramPct = Math.min(100, (t.vram_used_mb / Math.max(1, t.vram_total_mb)) * 100);
    vramVal.textContent = `${t.vram_used_mb.toFixed(0)} / ${t.vram_total_mb.toFixed(0)} MB`;
    vramBar.style.width = `${vramPct}%`;
    vramBar.classList.toggle("danger", t.vram_over_budget);
    vramAlert.classList.toggle("hidden", !t.vram_over_budget);
  } else {
    gpuVal.textContent = "n/a";
    vramVal.textContent = "n/a";
  }
}

// --- WebSocket Connection ---
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.kind === "init") {
      const s = msg.value;
      updateState(s.state);
      updateOnline(s.online);
      statusLine.textContent = s.status;
      workspaceInput.value = s.workspace || "";
      chatFeed.innerHTML = "";
      (s.chat_history || []).forEach(appendChat);
      if (s.telemetry) updateTelemetry(s.telemetry, s.tier);
    } else if (msg.kind === "state") {
      updateState(msg.value);
    } else if (msg.kind === "online") {
      updateOnline(msg.value);
    } else if (msg.kind === "status") {
      statusLine.textContent = msg.value;
    } else if (msg.kind === "level") {
      audioLevel = Number(msg.value) || 0;
    } else if (msg.kind === "chat") {
      appendChat(msg.value);
    } else if (msg.kind === "telemetry") {
      updateTelemetry(msg.value, msg.tier);
    }
  };

  ws.onclose = () => setTimeout(connectWS, 1500);
}
connectWS();

// --- Interactive Buttons & Forms ---
document.getElementById("wakeBtn").onclick = () => fetch("/api/wake", { method: "POST" });
document.getElementById("standDownBtn").onclick = () => fetch("/api/stand_down", { method: "POST" });
document.getElementById("clearMemBtn").onclick = () => fetch("/api/clear_memory", { method: "POST" });

document.getElementById("saveWsBtn").onclick = async () => {
  await fetch("/api/workspace", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace: workspaceInput.value }),
  });
};

chatForm.onsubmit = async (e) => {
  e.preventDefault();
  const text = chatInput.value.trim();
  if (!text) return;
  chatInput.value = "";
  await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
};

// --- Audio Settings Modal ---
const settingsModal = document.getElementById("settingsModal");
const inputSelect = document.getElementById("inputSelect");
const outputSelect = document.getElementById("outputSelect");

document.getElementById("settingsBtn").onclick = async () => {
  const res = await fetch("/api/devices");
  const data = await res.json();
  inputSelect.innerHTML = data.inputs.map((d) => `<option value="${d}">${d}</option>`).join("");
  outputSelect.innerHTML = data.outputs.map((d) => `<option value="${d}">${d}</option>`).join("");
  inputSelect.value = data.current_input;
  outputSelect.value = data.current_output;
  settingsModal.classList.remove("hidden");
};

document.getElementById("closeModalBtn").onclick = () => settingsModal.classList.add("hidden");
document.getElementById("applyDevicesBtn").onclick = async () => {
  await fetch("/api/devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      input_device: inputSelect.value,
      output_device: outputSelect.value,
    }),
  });
  settingsModal.classList.add("hidden");
};

// --- 60 FPS HTML5 Canvas Visualizer Sphere ---
const canvas = document.getElementById("sphereCanvas");
const ctx = canvas.getContext("2d");

function renderSphere() {
  const w = canvas.width;
  const h = canvas.height;
  const cx = w / 2;
  const cy = h / 2;

  ctx.clearRect(0, 0, w, h);

  const speedMap = { standby: 0.018, listening: 0.08, thinking: 0.05, speaking: 0.065 };
  phase += speedMap[atomState] || 0.025;
  arcAngle = (arcAngle + (atomState === "thinking" ? 6.5 : 1.4)) % 360;

  const rgb = online ? "0, 240, 255" : "255, 176, 0";
  const breathe = (Math.sin(phase * 2 * Math.PI) + 1) / 2;
  const coreRadius = 46 + 9 * breathe + 42 * audioLevel;

  // Concentric outer glow shells
  [0.08, 0.15, 0.26, 0.42].forEach((alpha, idx) => {
    const r = coreRadius + (4 - idx) * 18;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${rgb}, ${atomState === "standby" ? alpha * 0.55 : alpha})`;
    ctx.fill();
  });

  // Core sphere
  const grad = ctx.createRadialGradient(cx, cy, coreRadius * 0.1, cx, cy, coreRadius);
  grad.addColorStop(0, online ? "#e8feff" : "#fff3d1");
  grad.addColorStop(1, `rgba(${rgb}, ${atomState === "standby" ? 0.55 : 0.95})`);
  ctx.beginPath();
  ctx.arc(cx, cy, coreRadius, 0, Math.PI * 2);
  ctx.fillStyle = grad;
  ctx.fill();

  // Rotating tactical HUD arcs
  const arcR = coreRadius + 82;
  const startRad = (arcAngle * Math.PI) / 180;
  const extentRad = ((90 + 40 * breathe) * Math.PI) / 180;

  ctx.beginPath();
  ctx.arc(cx, cy, arcR, startRad, startRad + extentRad);
  ctx.strokeStyle = `rgba(${rgb}, 0.85)`;
  ctx.lineWidth = 2.5;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(cx, cy, arcR - 10, startRad + Math.PI, startRad + Math.PI + extentRad * 0.6);
  ctx.strokeStyle = `rgba(${rgb}, 0.42)`;
  ctx.lineWidth = 2;
  ctx.stroke();

  requestAnimationFrame(renderSphere);
}
requestAnimationFrame(renderSphere);
