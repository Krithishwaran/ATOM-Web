from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time
import urllib.request
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _sync_edge_clock() -> None:
    try:
        from edge_tts.drm import DRM
        req = urllib.request.Request("https://www.microsoft.com", method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as resp:
            date_hdr = resp.headers.get("Date")
            if date_hdr:
                server_ts = parsedate_to_datetime(date_hdr).timestamp()
                DRM.adj_clock_skew_seconds = server_ts - time.time()
                log.info("edge-tts clock synced (offset=%.1fs)", DRM.adj_clock_skew_seconds)
    except Exception as exc:
        log.debug("edge-tts clock sync skipped: %s", exc)


class TTSEngine:
    def __init__(self, voice: str = "en-IE-EmilyNeural", rate: str = "+0%",
                 output_device: Optional[str] = None,
                 offline_fallback: bool = True) -> None:
        self.voice = voice
        self.rate = rate
        self.offline_fallback = offline_fallback
        self._output_device = output_device
        self._mixer_ready = False
        self._offline_engine = None
        self._offline_speaking = False
        self._clock_synced = False
        self._tmp_files: list[Path] = []
        self._init_mixer(output_device)

    def _init_mixer(self, device: Optional[str]) -> None:
        import pygame
        kwargs = {"frequency": 24000, "size": -16, "channels": 1, "buffer": 512}
        if device:
            kwargs["devicename"] = device
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        pygame.mixer.init(**kwargs)
        self._mixer_ready = True
        self._output_device = device

    def set_output_device(self, device: Optional[str]) -> None:
        try:
            self._init_mixer(device)
        except Exception as exc:
            log.error("failed to switch output device: %s", exc)

    async def _synth_edge(self, text: str) -> Path:
        import edge_tts
        if not self._clock_synced:
            await asyncio.get_running_loop().run_in_executor(None, _sync_edge_clock)
            self._clock_synced = True

        fd, raw = tempfile.mkstemp(suffix=".mp3", prefix="atom_tts_")
        os.close(fd)
        path = Path(raw)
        kwargs = {"voice": self.voice}
        if self.rate and self.rate != "+0%":
            kwargs["rate"] = self.rate
        communicate = edge_tts.Communicate(text, **kwargs)
        await communicate.save(str(path))
        self._tmp_files.append(path)
        return path

    def _speak_offline_sync(self, text: str) -> None:
        import pyttsx3
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        try:
            engine = pyttsx3.init()
            self._offline_engine = engine
            engine.setProperty("rate", 185)
            engine.say(text)
            engine.runAndWait()
        except Exception as exc:
            log.error("offline TTS error: %s", exc)
        finally:
            self._offline_speaking = False
            self._offline_engine = None

    async def speak(self, text: str) -> None:
        if not text or not text.strip():
            return
        try:
            path = await asyncio.wait_for(self._synth_edge(text), timeout=10)
            if self._mixer_ready:
                import pygame
                try:
                    pygame.mixer.music.unload()
                except Exception:
                    pass
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.play()
                return
            raise RuntimeError("mixer not initialised")
        except Exception as exc:
            log.warning("edge-tts unavailable (%s); using offline voice", repr(exc))
            if not self.offline_fallback:
                return
            self._offline_speaking = True
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._speak_offline_sync, text)

    def is_playing(self) -> bool:
        if self._offline_speaking:
            return True
        if self._mixer_ready:
            import pygame
            try:
                return pygame.mixer.music.get_busy()
            except Exception:
                return False
        return False

    async def wait_done(self, poll_s: float = 0.03) -> None:
        while self.is_playing():
            await asyncio.sleep(poll_s)

    def stop(self) -> None:
        if self._mixer_ready:
            import pygame
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
        engine = self._offline_engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
            self._offline_speaking = False

    def cleanup(self) -> None:
        self.stop()
        if self._mixer_ready:
            import pygame
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass
        for p in self._tmp_files:
            try:
                p.unlink(missing_ok=True)
            except Exception:
                pass
        self._tmp_files.clear()
