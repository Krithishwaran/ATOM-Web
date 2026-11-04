from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = PROJECT_ROOT / "models"
WAKE_WORD_DIR = MODELS_DIR / "wake_word"
LOGS_DIR = PROJECT_ROOT / "logs"
DEFAULT_WORKSPACE = PROJECT_ROOT / "workspace"
CUSTOM_WAKE_MODEL = WAKE_WORD_DIR / "wake_up_atom.onnx"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    blocksize: int = 1280
    input_device: str | None = None
    output_device: str | None = None
    speech_rms_threshold: int = 500
    silence_ms: int = 700
    max_utterance_s: int = 30
    listen_timeout_s: int = 10
    followup_window_s: int = 25
    barge_in_enabled: bool = True
    barge_in_rms: int = 1800
    barge_in_min_ms: int = 240


@dataclass
class WakeWordConfig:
    phrase: str = "wake up atom"
    model_path: Path | None = None
    fallback_model: str = "hey_jarvis"
    threshold: float = 0.5
    inference_framework: str = "onnx"


@dataclass
class STTConfig:
    model_size: str = "base.en"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1
    vad_filter: bool = True


@dataclass
class TTSConfig:
    voice: str = "en-IE-EmilyNeural"
    rate: str = "+0%"
    offline_fallback: bool = True


@dataclass
class LLMConfig:
    groq_model: str = "llama-3.3-70b-versatile"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    ollama_model: str = "qwen2.5-coder:3b"
    ollama_num_gpu_layers: int = 33
    request_timeout_s: int = 20


@dataclass
class HardwareConfig:
    vram_budget_mb: int = 3072
    telemetry_interval_s: float = 1.0


@dataclass
class WebConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    auto_open_browser: bool = True


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    wakeword: WakeWordConfig = field(default_factory=WakeWordConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    hw: HardwareConfig = field(default_factory=HardwareConfig)
    web: WebConfig = field(default_factory=WebConfig)

    hotkey: str = "ctrl+shift+space"
    workspace: Path = DEFAULT_WORKSPACE
    groq_api_key: str = ""
    nvidia_api_key: str = ""


def load_config(env_file: Path | None = None) -> AppConfig:
    load_dotenv(env_file or PROJECT_ROOT / ".env")
    cfg = AppConfig()
    cfg.groq_api_key = os.getenv("GROQ_API_KEY", "")
    cfg.nvidia_api_key = os.getenv("NVIDIA_API_KEY", "")
    cfg.web.port = int(os.getenv("ATOM_PORT", "8000"))
    cfg.wakeword.model_path = CUSTOM_WAKE_MODEL if CUSTOM_WAKE_MODEL.exists() else None
    DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    return cfg
