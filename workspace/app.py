# _VERCEL_SHIM_V5
import os, sys, re, json, time, asyncio, inspect, mimetypes, traceback, importlib.util, importlib.abc, importlib.machinery
from pathlib import Path
from unittest.mock import MagicMock
import fastapi
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
_SRC = _ROOT / "src"

for _p in (str(_ROOT), str(_SRC), str(_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("HOME", "/tmp")

class _FallbackMockLoader(importlib.abc.Loader):
    def create_module(self, spec):
        m = MagicMock()
        m.__path__ = []
        m.__file__ = f"<mock:{spec.name}>"
        m.__name__ = spec.name
        m.__package__ = spec.name
        return m
    def exec_module(self, module):
        pass

class _FallbackMockFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in ("src", "workspace", "fastapi", "starlette", "pydantic", "uvicorn", "jinja2", "anyio"):
            return None
        return importlib.machinery.ModuleSpec(fullname, _FallbackMockLoader(), is_package=True)

# Append at the end of sys.meta_path so installed packages and src/ import normally first
sys.meta_path.append(_FallbackMockFinder())

_orig_makedirs = os.makedirs
def _safe_makedirs(name, mode=0o777, exist_ok=False):
    try:
        return _orig_makedirs(name, mode=mode, exist_ok=True)
    except OSError:
        return None
os.makedirs = _safe_makedirs

# 1. Index all HTML, CSS, JS, and static files in src/ (prioritized) and repo root
_HTML_FILES = []
_CSS_FILES = []
_STATIC_MAP = {}

def _scan_assets():
    search_roots = [_SRC, _ROOT] if _SRC.exists() else [_ROOT]
    seen = set()
    for base in search_roots:
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            s = str(p)
            if any(x in s for x in (".venv", ".git", "__pycache__", "node_modules")):
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
                    sub = "/".join(parts[i:])
                    _STATIC_MAP.setdefault(sub, p)

_scan_assets()

# 2. Capture FastAPI instances and routes from src/
_CAPTURED_APPS = []
_OrigFastAPIInit = fastapi.FastAPI.__init__

def _hooked_fastapi_init(self, *args, **kwargs):
    _OrigFastAPIInit(self, *args, **kwargs)
    _CAPTURED_APPS.append(self)

fastapi.FastAPI.__init__ = _hooked_fastapi_init

try:
    import uvicorn
    uvicorn.run = lambda *a, **kw: None
except Exception:
    pass

def _discover_src_apps():
    if not _SRC.exists():
        return
    py_files = sorted(_SRC.rglob("*.py"), key=lambda x: (0 if "server" in x.name or "web" in x.name or "hud" in x.name or "app" in x.name else 1, str(x)))
    for pyf in py_files:
        try:
            txt = pyf.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "FastAPI" not in txt and "APIRouter" not in txt and "websocket" not in txt:
            continue
        rel_mod = pyf.relative_to(_ROOT).with_suffix("").as_posix().replace("/", ".")
        try:
            mod = importlib.import_module(rel_mod)
            for _, obj in inspect.getmembers(mod):
                if inspect.isclass(obj) and obj.__module__ == mod.__name__:
                    try:
                        src_code = inspect.getsource(obj)
                        if "FastAPI" in src_code:
                            sig = inspect.signature(obj.__init__)
                            req_params = [
                                p for name, p in list(sig.parameters.items())[1:]
                                if p.default is inspect.Parameter.empty
                                and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                            ]
                            if not req_params:
                                obj()
                            else:
                                obj(*[MagicMock() for _ in req_params])
                    except Exception:
                        pass
                elif inspect.isfunction(obj) and obj.__module__ == mod.__name__:
                    try:
                        src_code = inspect.getsource(obj)
                        if "FastAPI(" in src_code:
                            sig = inspect.signature(obj)
                            req_params = [
                                p for name, p in sig.parameters.items()
                                if p.default is inspect.Parameter.empty
                                and p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                            ]
                            if not req_params:
                                obj()
                    except Exception:
                        pass
        except Exception:
            pass

_discover_src_apps()
fastapi.FastAPI.__init__ = _OrigFastAPIInit

app = FastAPI()

_WS_HANDLERS = []
for _cap in _CAPTURED_APPS:
    for _r in getattr(_cap, "routes", []):
        _rpath = getattr(_r, "path", "")
        if _r.__class__.__name__ == "APIWebSocketRoute" or "WebSocket" in _r.__class__.__name__:
            _WS_HANDLERS.append(_r.endpoint)
        elif _rpath not in ("", "/", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            app.router.routes.append(_r)

# 3. Client-side WebSocket-to-HTTP Bridge for Vercel Serverless
_WS_BRIDGE_JS = """
<script id="vercel-ws-bridge">
(function() {
  const OrigWS = window.WebSocket;
  class VercelServerlessWS {
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
      }, 120);
      this._timer = setInterval(() => {
        if (this.readyState === 1) this._poll('telemetry', {});
      }, 4000);
    }
    addEventListener(type, fn) {
      if (!this._listeners[type]) this._listeners[type] = [];
      this._listeners[type].push(fn);
    }
    removeEventListener(type, fn) {
      if (this._listeners[type]) {
        this._listeners[type] = this._listeners[type].filter(f => f !== fn);
      }
    }
    _emitMessage(obj) {
      const dataStr = typeof obj === 'string' ? obj : JSON.stringify(obj);
      const ev = { data: dataStr, type: 'message' };
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
          data.messages.forEach(m => this._emitMessage(m));
        }
      } catch (e) {}
    }
    send(data) {
      let parsed = data;
      try { parsed = JSON.parse(data); } catch(e) {}
      this._poll('message', parsed);
    }
    close() {
      this.readyState = 3;
      clearInterval(this._timer);
      const ev = new Event('close');
      if (this.onclose) try { this.onclose(ev); } catch(e) {}
      (this._listeners.close || []).forEach(fn => { try { fn(ev); } catch(e) {} });
    }
  }
  window.WebSocket = function(url, protocols) {
    if (typeof url === 'string' && (url.includes(location.host) || url.startsWith('ws://localhost') || url.startsWith('ws://127.0.0.1'))) {
      return new VercelServerlessWS(url);
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

class _FakeWebSocketDisconnect(Exception):
    pass

class _FakeWebSocket:
    def __init__(self, incoming=None):
        self.incoming = list(incoming or [])
        self.outgoing = []
        self.client_state = 1
    async def accept(self, *args, **kwargs):
        pass
    async def send_text(self, data: str):
        try:
            self.outgoing.append(json.loads(data))
        except Exception:
            self.outgoing.append(data)
    async def send_json(self, data, mode: str = "text"):
        self.outgoing.append(data)
    async def receive_text(self):
        if self.incoming:
            item = self.incoming.pop(0)
            return item if isinstance(item, str) else json.dumps(item)
        raise _FakeWebSocketDisconnect()
    async def receive_json(self, mode: str = "text"):
        if self.incoming:
            item = self.incoming.pop(0)
            return json.loads(item) if isinstance(item, str) else item
        raise _FakeWebSocketDisconnect()
    async def receive(self):
        if self.incoming:
            item = self.incoming.pop(0)
            txt = item if isinstance(item, str) else json.dumps(item)
            return {"type": "websocket.receive", "text": txt}
        raise _FakeWebSocketDisconnect()
    async def close(self, *args, **kwargs):
        pass

def _get_telemetry_payload():
    cpu = 14.2
    ram_used = 0.4
    ram_total = 7.0
    try:
        import psutil
        cpu = round(psutil.cpu_percent(interval=None) or 12.5, 1)
        vm = psutil.virtual_memory()
        ram_used = round(vm.used / (1024**3), 1)
        ram_total = round(vm.total / (1024**3), 1)
    except Exception:
        pass
    return {
        "type": "telemetry",
        "event": "telemetry",
        "status": "ONLINE",
        "tier": "Cloud Serverless",
        "state": "IDLE",
        "cpu": cpu,
        "cpu_load": cpu,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "ram_gb": f"{ram_used} / {ram_total}",
        "gpu": 0,
        "gpu_load": 0,
        "vram_used": 256,
        "vram_mb": 256,
        "vram_cap": 3072,
        "vram_exceeded": False,
        "budget_exceeded": False
    }

@app.post("/__atom_ws")
async def _handle_atom_ws(request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    action = body.get("action", "telemetry")
    payload = body.get("payload", {})
    messages = []

    if action in ("connect", "message") and _WS_HANDLERS:
        incoming = [payload] if action == "message" else []
        fake_ws = _FakeWebSocket(incoming=incoming)
        try:
            await asyncio.wait_for(_WS_HANDLERS[0](fake_ws), timeout=4.0)
        except (_FakeWebSocketDisconnect, asyncio.TimeoutError, Exception):
            pass
        if fake_ws.outgoing:
            messages.extend(fake_ws.outgoing)

    if action == "connect":
        messages.append(_get_telemetry_payload())
        messages.append({
            "type": "status",
            "status": "ONLINE",
            "tier": "Cloud Serverless",
            "state": "READY",
            "message": "ATOM Core Online (Vercel Serverless Mode)"
        })
        messages.append({
            "type": "transcript",
            "sender": "ATOM",
            "role": "assistant",
            "text": "A.T.O.M. Core initialized on Vercel Serverless. Ready for commands."
        })
    elif action == "telemetry":
        messages.append(_get_telemetry_payload())
    elif action == "message" and not messages:
        cmd_text = ""
        if isinstance(payload, dict):
            cmd_text = payload.get("text") or payload.get("command") or payload.get("prompt") or payload.get("message") or payload.get("action") or json.dumps(payload)
        else:
            cmd_text = str(payload)
        messages.append({
            "type": "transcript",
            "sender": "USER",
            "role": "user",
            "text": str(cmd_text)
        })
        messages.append({
            "type": "transcript",
            "sender": "ATOM",
            "role": "assistant",
            "text": f"Received command on Vercel Cloud node: '{cmd_text}'. (Configure LLM API keys in Vercel Environment Variables for full agent generation.)"
        })
    return JSONResponse({"messages": messages})

def _build_index_html():
    target_html = None
    for hf in _HTML_FILES:
        if hf.name.lower() == "index.html":
            target_html = hf
            break
    if not target_html and _HTML_FILES:
        target_html = _HTML_FILES[0]
    if not target_html:
        return "<html><body><h2>No HTML file found in repository</h2></body></html>"

    raw_html = target_html.read_text(encoding="utf-8", errors="ignore")
    css_blocks = []
    for cf in _CSS_FILES:
        try:
            css_blocks.append(f"/* {cf.name} */\n" + cf.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
    inlined_css = f"<style id='vercel-inlined-css'>\n" + "\n".join(css_blocks) + "\n</style>" if css_blocks else ""
    injection = inlined_css + "\n" + _WS_BRIDGE_JS
    if "</head>" in raw_html:
        raw_html = raw_html.replace("</head>", injection + "\n</head>", 1)
    else:
        raw_html = injection + "\n" + raw_html
    return raw_html

@app.get("/")
async def _serve_root():
    return HTMLResponse(content=_build_index_html(), status_code=200)

@app.get("/{full_path:path}")
async def _serve_static_or_fallback(full_path: str):
    clean = full_path.strip("/")
    if not clean or clean == "index.html":
        return HTMLResponse(content=_build_index_html(), status_code=200)

    cand = _STATIC_MAP.get(clean) or _STATIC_MAP.get(Path(clean).name)
    if cand and cand.exists():
        mime, _ = mimetypes.guess_type(str(cand))
        if cand.suffix.lower() == ".css":
            mime = "text/css; charset=utf-8"
        elif cand.suffix.lower() in (".js", ".mjs"):
            mime = "application/javascript; charset=utf-8"
        return Response(content=cand.read_bytes(), media_type=mime or "application/octet-stream")

    return JSONResponse({"status": "not_found", "path": clean}, status_code=404)