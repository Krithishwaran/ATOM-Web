# _VERCEL_SHIM_V2
import os, sys, traceback, importlib.abc, importlib.machinery
from pathlib import Path
from unittest.mock import MagicMock
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
import fastapi.staticfiles, starlette.staticfiles, fastapi.templating

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

def _resolve_dir(d):
    if not d:
        return d
    p = Path(d)
    for cand in (p, _DIR / p, _ROOT / p, _DIR / p.name, _ROOT / p.name):
        if cand.exists():
            return str(cand)
    return str(_DIR / p.name)

_OrigStatic = fastapi.staticfiles.StaticFiles
class _SafeStatic(_OrigStatic):
    def __init__(self, *args, **kwargs):
        if "directory" in kwargs:
            kwargs["directory"] = _resolve_dir(kwargs["directory"])
        elif args:
            args = (_resolve_dir(args[0]),) + args[1:]
        kwargs["check_dir"] = False
        super().__init__(*args, **kwargs)

fastapi.staticfiles.StaticFiles = _SafeStatic
starlette.staticfiles.StaticFiles = _SafeStatic

_OrigTemplates = fastapi.templating.Jinja2Templates
class _SafeTemplates(_OrigTemplates):
    def __init__(self, *args, **kwargs):
        if "directory" in kwargs:
            kwargs["directory"] = _resolve_dir(kwargs["directory"])
        elif args:
            args = (_resolve_dir(args[0]),) + args[1:]
        super().__init__(*args, **kwargs)

fastapi.templating.Jinja2Templates = _SafeTemplates

app = FastAPI()

try:
    import workspace._atom_app as _real_mod
    app = _real_mod.app
except BaseException:
    _tb = traceback.format_exc()
    print(_tb, file=sys.stderr)
    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def _vercel_diag(request: Request, path: str = ""):
        return HTMLResponse(
            content=f"<html><body style='background:#111;color:#f88;font-family:monospace;padding:24px;'>"
                    f"<h2>ATOM-Web Startup Error on Vercel</h2>"
                    f"<pre style='background:#222;color:#eee;padding:16px;border-radius:8px;overflow:auto;'>{_tb}</pre>"
                    f"</body></html>",
            status_code=200
        )