from __future__ import annotations

import asyncio
import logging
import re
import socket
import threading
import time

import numpy as np

from src.agent.coder import maybe_save_code
from src.audio.hotkeys import HotkeyTrigger
from src.audio.mic_router import MicRouter, rms
from src.audio.stt import UtteranceRecorder, WhisperSTT
from src.audio.tts import TTSEngine
from src.audio.wake_word import WakeWordEngine
from src.core.config import AppConfig
from src.core.state import AtomState, StateBus
from src.llm.router import Brain, RouterBrain

log = logging.getLogger(__name__)


def internet_available(timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=timeout):
            return True
    except OSError:
        return False


def _strip_code_for_speech(text: str) -> str:
    """Remove raw code blocks when speaking aloud so TTS only reads the explanation."""
    cleaned = re.sub(r"```.*?```", " I have written the code to your workspace. ", text, flags=re.DOTALL)
    cleaned = re.sub(r"FILE:\s*[^\n\r]+", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split()).strip() or "Task complete."


class AtomPipeline:
    def __init__(self, cfg: AppConfig, bus: StateBus, brain: Brain | None = None) -> None:
        self.cfg = cfg
        self.bus = bus
        self.brain: Brain = brain or RouterBrain(cfg)

        self._stop = threading.Event()
        self._stand_down_flag = threading.Event()
        self._workspace = cfg.workspace
        self._text_queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None

        self._router: MicRouter | None = None
        self._wake: WakeWordEngine | None = None
        self._stt: WhisperSTT | None = None
        self._recorder: UtteranceRecorder | None = None
        self.tts: TTSEngine | None = None
        self._hotkey = HotkeyTrigger(cfg.hotkey)

    # -- Web UI & External Control Hooks -------------------------------------
    def request_stop(self) -> None:
        self._stop.set()

    def trigger_wake(self) -> None:
        """Triggered from Web UI 'Wake / Interrupt' button or hotkey."""
        self._hotkey.trigger()

    def trigger_stand_down(self) -> None:
        """Triggered from Web UI 'Stand Down' button."""
        self._stand_down_flag.set()
        if self.tts:
            self.tts.stop()

    def submit_text_query(self, text: str) -> None:
        """Submit a typed prompt directly from the Web UI chat bar."""
        if self._loop and text.strip():
            self._loop.call_soon_threadsafe(self._text_queue.put_nowait, text.strip())

    def clear_memory(self) -> None:
        self.brain.clear_context()
        self.bus.status("Memory buffer purged.")

    def set_workspace(self, path: str) -> None:
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        self._workspace = p
        self.bus.status(f"Workspace: {self._workspace}")

    @property
    def workspace(self):
        return self._workspace

    def set_input_device(self, device: str | None) -> None:
        self.cfg.audio.input_device = device or None
        if self._router:
            self._router.request_device_change(device or None)

    def set_output_device(self, device: str | None) -> None:
        self.cfg.audio.output_device = device or None
        if self.tts:
            self.tts.set_output_device(device or None)

    # -- Main Async Engine Loop ----------------------------------------------
    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        self._loop = loop
        cfg = self.cfg

        self.bus.status("Booting ATOM core…")
        self._router = MicRouter(loop, cfg.audio.sample_rate,
                                 cfg.audio.blocksize, cfg.audio.input_device)
        self.tts = TTSEngine(cfg.tts.voice, cfg.tts.rate,
                             output_device=cfg.audio.output_device,
                             offline_fallback=cfg.tts.offline_fallback)
        self._stt = WhisperSTT(cfg.stt.model_size, cfg.stt.device,
                               cfg.stt.compute_type, cfg.stt.beam_size,
                               cfg.stt.vad_filter)

        self.bus.status("Loading Whisper STT model (CPU/int8)…")
        await loop.run_in_executor(None, self._stt.load)

        self.bus.status("Loading openWakeWord engine…")
        self._wake = await loop.run_in_executor(
            None,
            lambda: WakeWordEngine(cfg.wakeword.model_path,
                                   cfg.wakeword.fallback_model,
                                   cfg.wakeword.threshold,
                                   cfg.wakeword.inference_framework),
        )
        self._recorder = UtteranceRecorder(
            self._router, cfg.audio.sample_rate,
            cfg.audio.speech_rms_threshold, cfg.audio.silence_ms,
            cfg.audio.max_utterance_s,
            level_cb=self.bus.level,
            abort_check=lambda: self._stand_down_flag.is_set() or not self._text_queue.empty(),
        )

        self._hotkey.register()
        await loop.run_in_executor(None, self._router.start)
        self.bus.set_online(internet_available())
        self.bus.set_state(AtomState.STANDBY)
        self.bus.status('Standby. Say "Hey Jarvis", press Ctrl+Shift+Space, or use Web HUD.')

        try:
            await self._standby_loop()
        finally:
            self._shutdown()

    async def _standby_loop(self) -> None:
        assert self._router and self._wake
        while not self._stop.is_set():
            await self._router.maybe_restart()

            # Check if user submitted a text prompt via Web HUD
            if not self._text_queue.empty():
                text_query = await self._text_queue.get()
                await self._handle_turn(text_query)
                self.bus.set_state(AtomState.STANDBY)
                self.bus.status('Standby. Say "Hey Jarvis" or type below.')
                continue

            try:
                frame = await asyncio.wait_for(self._router.get_frame(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            hot = self._hotkey.consume()
            try:
                detected = self._wake.detected(frame)
            except Exception as exc:
                log.debug("wake-word inference error: %s", exc)
                detected = False

            if hot or detected:
                self._stand_down_flag.clear()
                self._router.flush()
                await self._conversation()

    async def _conversation(self) -> None:
        cfg = self.cfg
        first = True
        while not self._stop.is_set() and not self._stand_down_flag.is_set():
            if not self._text_queue.empty():
                text_query = await self._text_queue.get()
                await self._handle_turn(text_query)
                first = False
                continue

            timeout = (cfg.audio.listen_timeout_s if first else cfg.audio.followup_window_s)
            first = False

            self.bus.set_state(AtomState.LISTENING)
            self.bus.status("Listening… Speak now.")
            if self._router:
                self._router.flush()
            audio = await self._recorder.record(timeout)

            if self._stand_down_flag.is_set():
                break
            if not self._text_queue.empty():
                continue
            if audio is None:
                break

            self.bus.set_state(AtomState.THINKING)
            self.bus.status("Transcribing speech…")
            text = await asyncio.get_running_loop().run_in_executor(
                None, self._stt.transcribe_sync, audio
            )
            log.info("heard: %r", text)
            if not text:
                continue

            should_continue = await self._handle_turn(text)
            if not should_continue:
                break

        self._stand_down_flag.clear()
        self.bus.set_state(AtomState.STANDBY)
        self.bus.status('Standby. Say "Hey Jarvis" or press Ctrl+Shift+Space.')
        self.bus.level(0.0)
        if self._router:
            self._router.flush()

    async def _handle_turn(self, text: str) -> bool:
        """Process a user utterance or web text message. Returns False if session should end."""
        command = text.lower().strip().rstrip(".")
        self.bus.chat("user", text)

        if "stand down" in command:
            self.bus.chat("atom", "Standing down.", "System")
            await self._speak_and_monitor("Standing down.")
            return False

        if "clear your mind" in command:
            self.brain.clear_context()
            self.bus.chat("atom", "Memory buffer purged.", "System")
            await self._speak_and_monitor("Memory buffer purged.")
            return True

        online = await asyncio.get_running_loop().run_in_executor(None, internet_available)
        if online != self.bus.online:
            self.bus.set_online(online)
            if not online:
                self.bus.set_state(AtomState.OFFLINE)
                await self._speak_and_monitor("Connection lost. Switching to offline mode.")

        self.bus.set_state(AtomState.THINKING)
        self.bus.status(f"Thinking… ({text[:60]})")
        try:
            reply = await self.brain.respond(text)
        except Exception as exc:
            log.error("brain error: %s", exc)
            reply = "My reasoning core hit a fault. Try again."

        saved_file = maybe_save_code(reply, self._workspace)
        if saved_file:
            self.bus.status(f"Saved code to {saved_file.name}")

        self.bus.chat("atom", reply, getattr(self.brain, "last_tier", "LLM"))
        spoken_text = _strip_code_for_speech(reply)
        await self._speak_and_monitor(spoken_text)
        return True

    async def _speak_and_monitor(self, text: str) -> bool:
        cfg = self.cfg
        assert self.tts and self._router

        self.bus.set_state(AtomState.SPEAKING)
        self.bus.status(f"ATOM: {text[:90]}")
        await self.tts.speak(text)

        loud_run = 0
        needed = max(1, cfg.audio.barge_in_min_ms // 80)
        interrupted = False
        t0 = time.monotonic()

        while self.tts.is_playing() and not self._stop.is_set():
            if self._hotkey.consume() or self._stand_down_flag.is_set():
                self.tts.stop()
                interrupted = True
                break
            try:
                frame = await asyncio.wait_for(self._router.get_frame(), 0.05)
            except asyncio.TimeoutError:
                continue

            self.bus.level(0.45 + 0.3 * float(np.sin((time.monotonic() - t0) * 6)))

            if cfg.audio.barge_in_enabled:
                if rms(frame) >= cfg.audio.barge_in_rms:
                    loud_run += 1
                    if loud_run >= needed:
                        self.tts.stop()
                        interrupted = True
                        break
                else:
                    loud_run = 0

        await self.tts.wait_done()
        self.bus.level(0.0)
        return interrupted

    def _shutdown(self) -> None:
        self.bus.status("Shutting down.")
        self._hotkey.unregister()
        if self._router:
            self._router.stop()
        if self.tts:
            self.tts.cleanup()
