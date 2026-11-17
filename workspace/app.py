# _VERCEL_SHIM_V6
import os, sys, json, mimetypes, traceback
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
_JS_FILES = []
_STATIC_MAP = {}

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
                elif ext == ".js":
                    _JS_FILES.append(p)
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
    cpu = 14.5
    ram_used = 1.2
    ram_total = 7.0
    try:
        import psutil
        cpu = round(psutil.cpu_percent(interval=None) or 14.5, 1)
        vm = psutil.virtual_memory()
        ram_used = round(vm.used / (1024**3), 1)
        ram_total = round(vm.total / (1024**3), 1)
    except Exception:
        pass
    return {
        "type": "telemetry",
        "event": "telemetry",
        "status": "ONLINE",
        "state": "IDLE",
        "tier": "Tier 1: Groq Cloud",
        "cpu": cpu,
        "cpu_percent": cpu,
        "cpu_load": cpu,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "ram_percent": round((ram_used / max(ram_total, 0.1)) * 100, 1),
        "gpu": 8.0,
        "gpu_load": 8.0,
        "gpu_percent": 8.0,
        "vram_used": 412,
        "vram_mb": 412,
        "vram_total": 3072,
        "vram_cap": 3072,
        "vram_exceeded": False,
        "budget_exceeded": False
    }

def _query_cloud_llm(prompt_text: str) -> str:
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if groq_key:
        try:
            import requests
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "system", "content": "You are A.T.O.M. (Autonomous Tactical Operations Module), a concise, direct tactical AI assistant."},
                        {"role": "user", "content": prompt_text}
                    ],
                    "max_tokens": 512
                },
                timeout=8
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Groq API error: {e}"
    return (
        f"A.T.O.M. Cloud Node received: '{prompt_text}'. "
        "Add GROQ_API_KEY in Vercel -> Settings -> Environment Variables to enable live LLM responses."
    )

_BRIDGE_SCRIPT = """
<script id="atom-vercel-ws-bridge">
(function() {
  const OrigWS = window.WebSocket;
  class ServerlessWS {
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      this.onopen = null;
      this.onmessage = null;
      this.onclose = null;
      this.onerror = null;
      this._listeners = { open: [], message: [], close: [], error: [] };
      setTimeout(() => {
        this.readyState = 1;
        const ev = new Event('open');
        if (this.onopen) try { this.onopen(ev); } catch(e) {}
        this._listeners.open.forEach(fn => { try { fn(ev); } catch(e) {} });
        this._poll('connect', {});
      }, 80);
      this._timer = setInterval(() => {
        if (this.readyState === 1) this._poll('telemetry', {});
      }, 3500);
    }
    addEventListener(type, fn) {
      if (!this._listeners[type]) this._listeners[type] = [];
      this._listeners[type].push(fn);
    }
    removeEventListener(type, fn) {
      if (this._listeners[type]) this._listeners[type] = this._listeners[type].filter(f => f !== fn);
    }
    _emit(obj) {
      const str = typeof obj === 'string' ? obj : JSON.stringify(obj);
      const ev = { data: str, type: 'message' };
      if (this.onmessage) try { this.onmessage(ev); } catch(e) {}
      (this._listeners.message || []).forEach(fn => { try { fn(ev); } catch(e) {} });
    }
    async _poll(action, payload) {
      try {
        const res = await fetch('/__atom_ws', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action, payload })
        });
        if (!res.ok) return;
        const data = await res.json();
        if (Array.isArray(data.messages)) {
          data.messages.forEach(m => this._emit(m));
        }
      } catch(e) {}
    }
    send(data) {
      let parsed = data;
      try { parsed = JSON.parse(data); } catch(e) {}
      this._poll('message', parsed);
    }
    close() {
      this.readyState = 3;
      clearInterval(this._timer);
    }
  }
  window.WebSocket = function(url, protocols) {
    if (typeof url === 'string' && (url.includes(location.host) || url.includes('localhost') || url.includes('127.0.0.1') || url.startsWith('ws:'))) {
      return new ServerlessWS(url);
    }
    return new OrigWS(url, protocols);
  };
  window.WebSocket.OPEN = 1;
  window.WebSocket.CONNECTING = 0;
  window.WebSocket.CLOSING = 2;
  window.WebSocket.CLOSED = 3;
})();
</script>
"""

@app.post("/__atom_ws")
async def _atom_ws_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = body.get("action", "telemetry")
    payload = body.get("payload", {})
    telem = _get_telemetry()
    messages = [telem]

    if action == "connect":
        messages.append({
            "type": "status",
            "status": "ONLINE",
            "state": "IDLE",
            "tier": "Tier 1: Groq Cloud",
            "message": "A.T.O.M. Core Online (Vercel Cloud HUD)"
        })
        messages.append({
            "type": "transcript",
            "sender": "ATOM",
            "role": "assistant",
            "speaker": "ATOM",
            "text": "A.T.O.M. Cloud HUD initialized and ready."
        })
    elif action == "message":
        user_text = ""
        if isinstance(payload, dict):
            user_text = payload.get("text") or payload.get("command") or payload.get("prompt") or payload.get("message") or payload.get("query") or ""
            act = payload.get("action") or payload.get("type") or ""
            if not user_text and act:
                user_text = f"[{act}]"
        else:
            user_text = str(payload)
        if user_text:
            reply = _query_cloud_llm(str(user_text))
            messages.append({"type": "transcript", "sender": "USER", "role": "user", "speaker": "USER", "text": str(user_text)})
            messages.append({"type": "transcript", "sender": "ATOM", "role": "assistant", "speaker": "ATOM", "text": reply})
            messages.append({"type": "response", "text": reply, "reply": reply})
    return JSONResponse({"messages": messages, **telem})

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
    return JSONResponse({"status": "ok", "devices": {"inputs": ["Cloud Browser Mic"], "outputs": ["Cloud Browser Audio"]}, **telem})

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
    head_inject = style_block + "\n" + _BRIDGE_SCRIPT
    if "</head>" in html:
        html = html.replace("</head>", head_inject + "\n</head>", 1)
    else:
        html = head_inject + "\n" + html
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