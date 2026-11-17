# _VERCEL_SHIM_V7
import os, sys, json, random, mimetypes, traceback
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_SRC = _ROOT / "src"

os.environ.setdefault("HOME", "/tmp")

app = FastAPI()

_HTML_FILES = []
_CSS_FILES = []
_STATIC_MAP = {}
_RUNTIME_KEYS = {}

def _scan_repo_assets():
    roots = [_SRC, _ROOT] if _SRC.exists() else [_ROOT]
    seen = set()
    for base in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            try:
                if not p.is_file():
                    continue
                s = str(p)
                if any(part in s for part in (".venv", ".git", "__pycache__", "node_modules")):
                    continue
                if base == _ROOT and str(p).startswith(str(_DIR)):
                    continue
                if p in seen:
                    continue
                seen.add(p)
                ext = p.suffix.lower()
                if ext == ".html":
                    _HTML_FILES.append(p)
                elif ext == ".css":
                    _CSS_FILES.append(p)
                if ext in (".css", ".js", ".mjs", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".gif", ".webp", ".woff", ".woff2", ".ttf", ".mp3", ".wav", ".ogg", ".json"):
                    rel_root = p.relative_to(_ROOT).as_posix()
                    _STATIC_MAP.setdefault(rel_root, p)
                    _STATIC_MAP.setdefault(p.name, p)
                    if _SRC.exists() and str(p).startswith(str(_SRC)):
                        rel_src = p.relative_to(_SRC).as_posix()
                        _STATIC_MAP.setdefault(rel_src, p)
                    parts = rel_root.split("/")
                    for i in range(1, len(parts)):
                        _STATIC_MAP.setdefault("/".join(parts[i:]), p)
            except Exception:
                continue

_scan_repo_assets()

def _get_telemetry():
    cpu = round(random.uniform(11.0, 24.0), 1)
    ram_used = 6.4
    ram_total = 16.0
    try:
        import psutil
        c = psutil.cpu_percent(interval=None)
        if c and c > 0:
            cpu = round(c, 1)
    except Exception:
        pass
    gpu = round(random.uniform(6.0, 14.0), 1)
    vram_used = random.randint(410, 485)
    vram_cap = 3072
    has_groq = bool(os.environ.get("GROQ_API_KEY") or _RUNTIME_KEYS.get("GROQ_API_KEY"))
    return {
        "type": "telemetry",
        "event": "telemetry",
        "status": "ONLINE",
        "state": "IDLE",
        "tier": "Tier 1: Groq Cloud" if has_groq else "Tier 1: Cloud HUD",
        "cpu": cpu,
        "cpu_percent": cpu,
        "cpu_load": cpu,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "ram_percent": round((ram_used / ram_total) * 100, 1),
        "gpu": gpu,
        "gpu_load": gpu,
        "gpu_percent": gpu,
        "vram_used": vram_used,
        "vram_mb": vram_used,
        "vram_total": vram_cap,
        "vram_cap": vram_cap,
        "vram_percent": round((vram_used / vram_cap) * 100, 1),
        "vram_exceeded": False,
        "budget_exceeded": False
    }

def _query_cloud_llm(prompt_text: str, client_key: str = "") -> str:
    groq_key = (client_key or _RUNTIME_KEYS.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY") or "").strip()
    if groq_key:
        try:
            import requests
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are A.T.O.M. (Autonomous Tactical Operations Module), a fast, concise, high-tech AI assistant built by Krithishwaran. Respond clearly and directly."
                        },
                        {"role": "user", "content": prompt_text}
                    ],
                    "max_tokens": 600
                },
                timeout=9
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            return f"Groq API returned HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            return f"Groq connection error: {e}"

    return (
        f"Command acknowledged: \"{prompt_text}\". "
        "To enable full Llama-3.3-70B intelligence on Vercel, either paste your gsk_... key into the CODING AGENT WORKSPACE box on the bottom-left and click SET, or add GROQ_API_KEY in Vercel -> Settings -> Environment Variables."
    )

@app.post("/__atom_ws")
async def _atom_ws_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = body.get("action", "telemetry")
    payload = body.get("payload", {})
    client_key = body.get("apiKey", "").strip()
    if client_key.startswith("gsk_"):
        _RUNTIME_KEYS["GROQ_API_KEY"] = client_key

    telem = _get_telemetry()
    messages = [telem]

    if action == "connect":
        messages.append({
            "type": "status",
            "status": "ONLINE",
            "state": "IDLE",
            "tier": telem["tier"],
            "message": "A.T.O.M. Core Online — Ready for Commands"
        })
    elif action == "message":
        user_text = ""
        if isinstance(payload, dict):
            user_text = (
                payload.get("text")
                or payload.get("command")
                or payload.get("prompt")
                or payload.get("message")
                or payload.get("query")
                or ""
            )
        else:
            user_text = str(payload)
        user_text = str(user_text).strip()
        if user_text:
            reply = _query_cloud_llm(user_text, client_key=client_key)
            messages.append({"type": "transcript", "sender": "USER", "role": "user", "text": user_text})
            messages.append({"type": "transcript", "sender": "ATOM", "role": "assistant", "text": reply})
            return JSONResponse({"status": "ok", "reply": reply, "messages": messages, **telem})

    return JSONResponse({"status": "ok", "messages": messages, **telem})

@app.api_route("/api/{rest:path}", methods=["GET", "POST"])
async def _api_catchall(request: Request, rest: str):
    telem = _get_telemetry()
    if request.method == "POST":
        try:
            body = await request.json()
        except Exception:
            body = {}
        prompt = body.get("text") or body.get("command") or body.get("prompt") or body.get("message") or ""
        if prompt:
            reply = _query_cloud_llm(str(prompt))
            return JSONResponse({"status": "ok", "reply": reply, "text": reply, "response": reply, **telem})
    return JSONResponse({"status": "ok", "devices": {"inputs": ["Browser Microphone"], "outputs": ["System Default Output"]}, **telem})

_HEAD_WS_SHIM = """
<script id="atom-ws-interceptor">
(function() {
  const OrigWS = window.WebSocket;
  class NoopWS {
    constructor(url) {
      this.url = url;
      this.readyState = 1;
      setTimeout(() => {
        if (typeof this.onopen === 'function') {
          try { this.onopen(new Event('open')); } catch(e) {}
        }
      }, 50);
    }
    addEventListener(t, fn) { if (t === 'open') setTimeout(() => { try { fn(new Event('open')); } catch(e) {} }, 50); }
    removeEventListener() {}
    send(data) {
      if (window.__atomSendFromWS) window.__atomSendFromWS(data);
    }
    close() { this.readyState = 3; }
  }
  window.WebSocket = function(url, protocols) {
    return new NoopWS(url);
  };
  window.WebSocket.OPEN = 1;
  window.WebSocket.CONNECTING = 0;
  window.WebSocket.CLOSING = 2;
  window.WebSocket.CLOSED = 3;
})();
</script>
"""

_BODY_HUD_CONTROLLER = """
<script id="atom-vercel-hud-controller">
(function() {
  let tierEl = null, bootBadgeEl = null, centerBootEl = null;
  let cpuValEl = null, ramValEl = null, gpuValEl = null, vramValEl = null;
  let cpuBarEl = null, ramBarEl = null, gpuBarEl = null, vramBarEl = null;
  let transcriptBox = null, cmdInput = null, sendBtn = null;
  let wsInput = null, wsSetBtn = null;
  let isStandby = false;

  function findBarNear(valNode) {
    if (!valNode) return null;
    let row = valNode.parentElement;
    for (let d = 0; d < 3 && row; d++) {
      const candidates = row.querySelectorAll('div, span');
      for (const c of candidates) {
        if (c === valNode || c.contains(valNode)) continue;
        const cls = (c.className || '').toString().toLowerCase();
        const id = (c.id || '').toLowerCase();
        if (cls.includes('fill') || cls.includes('bar') || cls.includes('prog') || id.includes('bar') || id.includes('fill')) {
          if (c.children.length === 0) return c;
        }
      }
      row = row.parentElement;
    }
    return null;
  }

  function locateElements() {
    const all = document.querySelectorAll('*');
    const dashPercentEls = [];
    for (const el of all) {
      if (el.children.length === 0) {
        const t = (el.textContent || '').trim();
        if (t === 'Tier: Standby' || t.startsWith('Tier:')) tierEl = el;
        else if (t === 'BOOTING') bootBadgeEl = el;
        else if (t.includes('Booting ATOM core')) centerBootEl = el;
        else if (t === '--%') dashPercentEls.push(el);
        else if (t === '-- / -- GB' || t.endsWith('GB') && t.includes('--')) ramValEl = el;
        else if (t === '-- / -- MB' || t.endsWith('MB') && t.includes('--')) vramValEl = el;
        else if (t === 'SEND' && el.tagName === 'BUTTON') sendBtn = el;
        else if (t === 'SET' && el.tagName === 'BUTTON') wsSetBtn = el;
      }
      if (el.tagName === 'INPUT') {
        const ph = (el.getAttribute('placeholder') || '').toLowerCase();
        if (ph.includes('command') || ph.includes('prompt')) cmdInput = el;
        else if (!wsInput) wsInput = el;
      }
    }
    if (dashPercentEls.length >= 1) cpuValEl = dashPercentEls[0];
    if (dashPercentEls.length >= 2) gpuValEl = dashPercentEls[1];

    cpuBarEl = document.getElementById('cpu-bar') || document.getElementById('cpuBar') || findBarNear(cpuValEl);
    ramBarEl = document.getElementById('ram-bar') || document.getElementById('ramBar') || findBarNear(ramValEl);
    gpuBarEl = document.getElementById('gpu-bar') || document.getElementById('gpuBar') || findBarNear(gpuValEl);
    vramBarEl = document.getElementById('vram-bar') || document.getElementById('vramBar') || findBarNear(vramValEl);

    transcriptBox = document.getElementById('transcript')
      || document.getElementById('chat-stream')
      || document.getElementById('transcript-stream')
      || document.getElementById('messages')
      || document.getElementById('log')
      || document.querySelector('.transcript-stream, .transcript-list, .chat-messages, .messages, .stream-box, .transcript');

    if (!transcriptBox && cmdInput) {
      let panel = cmdInput.parentElement ? cmdInput.parentElement.parentElement : null;
      if (panel) {
        for (const child of panel.children) {
          if (child !== cmdInput.parentElement && !child.textContent.includes('NEURAL TRANSCRIPT')) {
            transcriptBox = child;
            break;
          }
        }
      }
    }
  }

  function appendTranscript(sender, text) {
    if (!transcriptBox) return;
    const item = document.createElement('div');
    const isAtom = sender === 'ATOM' || sender === 'SYSTEM';
    item.style.cssText = 'margin:8px 0;padding:10px 12px;border-radius:6px;font-size:13px;line-height:1.45;border-left:3px solid ' +
      (isAtom ? '#00f0ff' : '#8899aa') + ';background:' + (isAtom ? 'rgba(0,240,255,0.07)' : 'rgba(255,255,255,0.04)') + ';color:#e6f7ff;word-break:break-word;';
    const tag = document.createElement('div');
    tag.style.cssText = 'font-size:10px;font-weight:700;letter-spacing:1px;margin-bottom:4px;color:' + (isAtom ? '#00f0ff' : '#a0b8c8') + ';';
    tag.textContent = sender + ' // ' + new Date().toLocaleTimeString();
    const body = document.createElement('div');
    body.textContent = text;
    item.appendChild(tag);
    item.appendChild(body);
    transcriptBox.appendChild(item);
    transcriptBox.scrollTop = transcriptBox.scrollHeight;
  }

  function applyTelemetry(data) {
    if (isStandby) return;
    if (tierEl && data.tier) tierEl.textContent = data.tier;
    if (bootBadgeEl) {
      bootBadgeEl.textContent = data.status || 'ONLINE';
      bootBadgeEl.style.color = '#00f0ff';
      bootBadgeEl.style.borderColor = '#00f0ff';
      bootBadgeEl.style.boxShadow = '0 0 8px rgba(0,240,255,0.35)';
    }
    if (centerBootEl) {
      centerBootEl.textContent = 'A.T.O.M. Core Online — Ready';
      centerBootEl.style.color = '#00f0ff';
    }
    const cpu = data.cpu ?? 14.2;
    const ramUsed = data.ram_used ?? 6.4;
    const ramTotal = data.ram_total ?? 16.0;
    const gpu = data.gpu ?? 8.5;
    const vramUsed = data.vram_used ?? 420;
    const vramCap = data.vram_cap ?? 3072;

    if (cpuValEl) cpuValEl.textContent = cpu + '%';
    if (ramValEl) ramValEl.textContent = ramUsed + ' / ' + ramTotal + ' GB';
    if (gpuValEl) gpuValEl.textContent = gpu + '%';
    if (vramValEl) vramValEl.textContent = vramUsed + ' / ' + vramCap + ' MB';

    if (cpuBarEl) cpuBarEl.style.width = Math.min(100, cpu) + '%';
    if (ramBarEl) ramBarEl.style.width = Math.min(100, Math.round((ramUsed / ramTotal) * 100)) + '%';
    if (gpuBarEl) gpuBarEl.style.width = Math.min(100, gpu) + '%';
    if (vramBarEl) vramBarEl.style.width = Math.min(100, Math.round((vramUsed / vramCap) * 100)) + '%';
  }

  async function pollTelemetry(action = 'telemetry') {
    try {
      const savedKey = localStorage.getItem('ATOM_GROQ_KEY') || '';
      const res = await fetch('/__atom_ws', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, apiKey: savedKey })
      });
      if (!res.ok) return;
      const data = await res.json();
      applyTelemetry(data);
    } catch (e) {}
  }

  let sendingLock = false;
  async function sendUserCommand(rawText) {
    const text = (rawText || '').trim();
    if (!text || sendingLock) return;
    sendingLock = true;
    isStandby = false;
    appendTranscript('YOU', text);
    if (centerBootEl) centerBootEl.textContent = 'Processing Neural Request...';
    try {
      const savedKey = localStorage.getItem('ATOM_GROQ_KEY') || '';
      const res = await fetch('/__atom_ws', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'message', payload: { text }, apiKey: savedKey })
      });
      const data = await res.json();
      applyTelemetry(data);
      const reply = data.reply || 'Command processed.';
      appendTranscript('ATOM', reply);
      if ('speechSynthesis' in window) {
        try {
          window.speechSynthesis.cancel();
          const u = new SpeechSynthesisUtterance(reply);
          u.rate = 1.05;
          window.speechSynthesis.speak(u);
        } catch (e) {}
      }
    } catch (e) {
      appendTranscript('SYSTEM', 'Network error communicating with Vercel function.');
    } finally {
      sendingLock = false;
      if (centerBootEl) centerBootEl.textContent = 'A.T.O.M. Core Online — Ready';
    }
  }

  window.__atomSendFromWS = function(raw) {
    try {
      const obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
      const txt = obj.text || obj.command || obj.prompt || obj.message;
      if (txt) sendUserCommand(txt);
    } catch (e) {}
  };

  function wireControls() {
    if (sendBtn && cmdInput) {
      sendBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        const val = cmdInput.value;
        cmdInput.value = '';
        sendUserCommand(val);
      }, true);
      cmdInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.stopImmediatePropagation();
          const val = cmdInput.value;
          cmdInput.value = '';
          sendUserCommand(val);
        }
      }, true);
    }

    if (wsSetBtn && wsInput) {
      wsSetBtn.addEventListener('click', (e) => {
        e.preventDefault();
        const val = (wsInput.value || '').trim();
        if (!val) return;
        if (val.startsWith('gsk_')) {
          localStorage.setItem('ATOM_GROQ_KEY', val);
          wsInput.value = '';
          wsInput.placeholder = 'Groq API Key Saved!';
          appendTranscript('SYSTEM', 'Groq API key saved in browser session. Live Llama-3.3-70B responses enabled.');
          pollTelemetry('connect');
        } else {
          appendTranscript('SYSTEM', 'Workspace path set to: ' + val);
        }
      }, true);
    }

    const buttons = document.querySelectorAll('button');
    for (const b of buttons) {
      const label = (b.textContent || '').trim().toUpperCase();
      if (label.includes('WAKE') || label.includes('INTERRUPT')) {
        b.addEventListener('click', () => {
          isStandby = false;
          if ('speechSynthesis' in window) window.speechSynthesis.cancel();
          const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
          if (SR) {
            try {
              const rec = new SR();
              rec.lang = 'en-US';
              if (centerBootEl) centerBootEl.textContent = 'Listening via Browser Mic...';
              if (bootBadgeEl) bootBadgeEl.textContent = 'LISTENING';
              rec.onresult = (ev) => {
                const transcript = ev.results[0][0].transcript;
                sendUserCommand(transcript);
              };
              rec.onerror = () => {
                if (centerBootEl) centerBootEl.textContent = 'A.T.O.M. Core Online — Ready';
                if (cmdInput) cmdInput.focus();
              };
              rec.start();
              return;
            } catch (e) {}
          }
          if (cmdInput) cmdInput.focus();
          appendTranscript('SYSTEM', 'A.T.O.M. awake and listening. Type your command below.');
        });
      } else if (label.includes('STAND DOWN')) {
        b.addEventListener('click', () => {
          isStandby = true;
          if ('speechSynthesis' in window) window.speechSynthesis.cancel();
          if (bootBadgeEl) bootBadgeEl.textContent = 'STANDBY';
          if (centerBootEl) centerBootEl.textContent = 'System in Standby Mode';
          appendTranscript('SYSTEM', 'A.T.O.M. standing down to standby mode.');
        });
      } else if (label.includes('CLEAR MIND')) {
        b.addEventListener('click', () => {
          if (transcriptBox) transcriptBox.innerHTML = '';
          appendTranscript('SYSTEM', 'Neural transcript & session context cleared.');
        });
      }
    }
  }

  function initHUD() {
    locateElements();
    wireControls();
    applyTelemetry({
      tier: localStorage.getItem('ATOM_GROQ_KEY') ? 'Tier 1: Groq Cloud' : 'Tier 1: Cloud HUD',
      status: 'ONLINE',
      cpu: 14.2,
      ram_used: 6.4,
      ram_total: 16.0,
      gpu: 8.0,
      vram_used: 412,
      vram_cap: 3072
    });
    appendTranscript('ATOM', 'A.T.O.M. Cloud HUD online. Type a command on the bottom-right or click WAKE / INTERRUPT to speak.');
    pollTelemetry('connect');
    setInterval(() => pollTelemetry('telemetry'), 4000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => setTimeout(initHUD, 150));
  } else {
    setTimeout(initHUD, 150);
  }
})();
</script>
"""

def _render_hud_html() -> str:
    chosen = None
    for hf in _HTML_FILES:
        try:
            txt = hf.read_text(encoding="utf-8", errors="ignore")
            if "A.T.O.M" in txt or "HUD" in txt or "TELEMETRY" in txt:
                chosen = hf
                break
        except Exception:
            pass
    if not chosen and _HTML_FILES:
        chosen = _HTML_FILES[0]
    if not chosen:
        return "<html><body style='background:#05080d;color:#00f0ff;font-family:monospace;padding:24px;'><h2>A.T.O.M. HUD HTML file not found in repository</h2></body></html>"

    html = chosen.read_text(encoding="utf-8", errors="ignore")
    css_parts = []
    for cf in _CSS_FILES:
        try:
            css_parts.append(f"/* {cf.name} */\n" + cf.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    style_block = f"<style id='atom-vercel-css'>\n" + "\n".join(css_parts) + "\n</style>" if css_parts else ""
    head_inject = style_block + "\n" + _HEAD_WS_SHIM
    if "</head>" in html:
        html = html.replace("</head>", head_inject + "\n</head>", 1)
    else:
        html = head_inject + "\n" + html

    if "</body>" in html:
        html = html.replace("</body>", _BODY_HUD_CONTROLLER + "\n</body>", 1)
    else:
        html = html + "\n" + _BODY_HUD_CONTROLLER
    return html

@app.get("/")
async def _root():
    try:
        return HTMLResponse(content=_render_hud_html(), status_code=200)
    except Exception:
        tb = traceback.format_exc()
        return HTMLResponse(content=f"<pre>{tb}</pre>", status_code=200)

@app.get("/{full_path:path}")
async def _static_handler(full_path: str):
    clean = full_path.strip("/")
    if not clean or clean == "index.html":
        return HTMLResponse(content=_render_hud_html(), status_code=200)
    cand = _STATIC_MAP.get(clean) or _STATIC_MAP.get(Path(clean).name)
    if cand and cand.exists():
        mime, _ = mimetypes.guess_type(str(cand))
        ext = cand.suffix.lower()
        if ext == ".css":
            mime = "text/css; charset=utf-8"
        elif ext in (".js", ".mjs"):
            mime = "application/javascript; charset=utf-8"
        return Response(content=cand.read_bytes(), media_type=mime or "application/octet-stream")
    return JSONResponse({"error": "not_found", "path": clean}, status_code=404)