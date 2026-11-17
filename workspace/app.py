# _VERCEL_SHIM_V4
import os, sys, shutil, sqlite3, builtins, traceback, importlib.abc, importlib.machinery
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent
for _p in (str(_DIR), str(_ROOT), str(_ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("HOME", "/tmp")

_MOCK_PKGS = {
    "openwakeword", "tflite_runtime", "onnxruntime", "scipy", "sklearn",
    "realtimestt", "realtimetts", "faster_whisper", "whisper", "torch",
    "torchaudio", "torchvision", "pvporcupine", "vosk", "speech_recognition",
    "webrtcvad", "silero_vad", "pyaudio", "win32api", "win32com", "win32gui",
    "win32con", "win32process", "pywintypes", "pythoncom", "comtypes",
    "pycaw", "pyttsx3", "playsound", "sounddevice", "soundfile", "pygame",
    "pyautogui", "pynput", "keyboard", "mouse", "mss", "cv2", "winsound",
    "alsaaudio", "pywhatkit", "AppOpener", "wmi", "screen_brightness_control"
}

class _MockLoader(importlib.abc.Loader):
    def create_module(self, spec):
        m = MagicMock()
        m.__path__ = []
        m.__file__ = f"<mock:{spec.name}>"
        m.__name__ = spec.name
        m.__package__ = spec.name
        return m
    def exec_module(self, module):
        pass

class _MockFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in _MOCK_PKGS or root.lower() in _MOCK_PKGS:
            return importlib.machinery.ModuleSpec(fullname, _MockLoader(), is_package=True)
        return None

sys.meta_path.append(_MockFinder())

_orig_makedirs = os.makedirs
def _safe_makedirs(name, mode=0o777, exist_ok=False):
    try:
        return _orig_makedirs(name, mode=mode, exist_ok=True)
    except OSError:
        return None
os.makedirs = _safe_makedirs

_orig_sqlite_connect = sqlite3.connect
def _safe_sqlite_connect(database, *args, **kwargs):
    db_str = str(database)
    if db_str != ":memory:" and not db_str.startswith("/tmp"):
        p = Path(db_str)
        if not p.is_absolute():
            p = _DIR / p
        tmp_db = Path("/tmp") / p.name
        if not tmp_db.exists() and p.exists():
            try:
                shutil.copy2(p, tmp_db)
            except Exception:
                pass
        return _orig_sqlite_connect(str(tmp_db), *args, **kwargs)
    return _orig_sqlite_connect(database, *args, **kwargs)
sqlite3.connect = _safe_sqlite_connect

_orig_open = builtins.open
def _safe_open(file, mode="r", *args, **kwargs):
    try:
        if isinstance(file, (str, Path)):
            p = Path(file)
            if not p.is_absolute():
                p = _DIR / p
            if str(p).startswith(str(_ROOT)):
                tmp_p = Path("/tmp") / p.name
                if any(m in mode for m in ("w", "a", "x", "+")):
                    if not tmp_p.exists() and p.exists():
                        try:
                            shutil.copy2(p, tmp_p)
                        except Exception:
                            pass
                    return _orig_open(tmp_p, mode, *args, **kwargs)
                if "r" in mode and not p.exists() and tmp_p.exists():
                    return _orig_open(tmp_p, mode, *args, **kwargs)
    except Exception:
        pass
    return _orig_open(file, mode, *args, **kwargs)
builtins.open = _safe_open

app = FastAPI()

try:
    os.chdir(_DIR)
    import workspace._atom_app as _real_mod
    _target = getattr(_real_mod, "app", None)
    from flask import Flask
    import jinja2
    if isinstance(_target, Flask):
        if not _target.secret_key:
            _target.secret_key = os.environ.get("SECRET_KEY", "atom-vercel-secret-key")
        _html_dirs = []
        for _cand in (_DIR / "templates", _DIR, _ROOT / "templates", _ROOT):
            if _cand.exists() and str(_cand) not in _html_dirs:
                _html_dirs.append(str(_cand))
        for _hf in _ROOT.rglob("*.html"):
            _parent = str(_hf.parent)
            if ".venv" not in _parent and _parent not in _html_dirs:
                _html_dirs.append(_parent)
        if _html_dirs:
            _target.jinja_loader = jinja2.ChoiceLoader([jinja2.FileSystemLoader(_html_dirs)])
        for _sdir in (_DIR / "static", _ROOT / "static", _ROOT / "src" / "static"):
            if _sdir.exists():
                _target.static_folder = str(_sdir)
                break
        @_target.errorhandler(Exception)
        def _flask_err(e):
            from werkzeug.exceptions import HTTPException
            if isinstance(e, HTTPException):
                return e
            tb = traceback.format_exc()
            py_files = [str(p.relative_to(_ROOT)) for p in _ROOT.rglob("*.py") if ".venv" not in str(p)]
            html_files = [str(p.relative_to(_ROOT)) for p in _ROOT.rglob("*.html") if ".venv" not in str(p)]
            return (
                f"<html><body style='background:#111;color:#f88;font-family:monospace;padding:24px;'>"
                f"<h2>Flask Route Error on Vercel</h2>"
                f"<pre style='background:#222;color:#eee;padding:16px;border-radius:8px;overflow:auto;'>{tb}</pre>"
                f"<h3 style='color:#8cf;'>Repository Files Detected</h3>"
                f"<pre style='background:#222;color:#ccc;padding:16px;border-radius:8px;'>Python: {py_files}\nHTML: {html_files}</pre>"
                f"</body></html>",
                200
            )
        from a2wsgi import WSGIMiddleware
        app = FastAPI()
        app.mount("/", WSGIMiddleware(_target))
    elif _target is not None:
        app = _target
except BaseException:
    _tb = traceback.format_exc()
    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def _vercel_diag(request: Request, path: str = ""):
        return HTMLResponse(
            content=f"<html><body style='background:#111;color:#f88;font-family:monospace;padding:24px;'>"
                    f"<h2>ATOM-Web Startup Error on Vercel</h2>"
                    f"<pre style='background:#222;color:#eee;padding:16px;border-radius:8px;overflow:auto;'>{_tb}</pre>"
                    f"</body></html>",
            status_code=200
        )