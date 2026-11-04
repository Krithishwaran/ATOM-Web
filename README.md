# ATOM-Web (Localhost Web HUD Edition)

**A.T.O.M. Web** is an autonomous desktop AI voice assistant and coding agent for Windows 11.
It replaces the desktop CustomTkinter window with a real-time **FastAPI + WebSocket localhost HUD** (`http://127.0.0.1:8000`) while preserving the hardware budget:

- **CPU**: Wake word (`openWakeWord`), STT (`faster-whisper` int8), telemetry, FastAPI + WebSocket server
- **GPU (RTX 2050 4 GB)**: Reserved strictly for Tier 3 local LLM (`ollama`) with a **3.0 GB (3072 MB) VRAM watchdog**
- **Localhost Web HUD**: 60 FPS HTML5 Canvas reactive sphere, live CPU/RAM/GPU/VRAM telemetry bars, live conversation transcript, text + voice input, audio device switcher, and workspace coding agent controls.

## Quick Start (Windows 11 PowerShell)

```powershell
cd ATOM-Web
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser -Force
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Add your GROQ_API_KEY to .env
python -m src.main
```

Your browser will automatically open `http://127.0.0.1:8000`.
