"""
ATOM-Web entry point.

Threading model:
  - Main thread:    FastAPI + Uvicorn server on http://127.0.0.1:8000
  - Daemon thread:  asyncio voice/LLM pipeline (openWakeWord -> Whisper -> 3-Tier LLM -> TTS)
  - Browser:        Automatically opens http://127.0.0.1:8000 on launch
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn

from src.core.config import LOGS_DIR, load_config
from src.core.state import StateBus


def _setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(LOGS_DIR / "atom.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def main() -> None:
    _setup_logging()
    log = logging.getLogger("atom-web")
    cfg = load_config()
    bus = StateBus()

    from src.audio.pipeline import AtomPipeline
    from src.web.server import create_app

    pipeline = AtomPipeline(cfg, bus)
    app = create_app(cfg, bus, pipeline)

    engine = threading.Thread(
        target=lambda: asyncio.run(pipeline.run()),
        name="atom-engine",
        daemon=True,
    )
    engine.start()

    url = f"http://{cfg.web.host}:{cfg.web.port}"
    log.info("ATOM-Web HUD live at %s", url)
    if cfg.web.auto_open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()

    try:
        uvicorn.run(app, host=cfg.web.host, port=cfg.web.port, log_level="warning")
    finally:
        pipeline.request_stop()
        engine.join(timeout=5)
        log.info("ATOM-Web shutdown complete")


if __name__ == "__main__":
    main()
