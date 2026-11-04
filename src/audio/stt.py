from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import numpy as np

from src.audio.mic_router import MicRouter, rms

log = logging.getLogger(__name__)


class WhisperSTT:
    def __init__(self, model_size: str = "base.en", device: str = "cpu",
                 compute_type: str = "int8", beam_size: int = 1,
                 vad_filter: bool = True) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.vad_filter = vad_filter
        self._model = None

    def load(self) -> None:
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            self.model_size, device=self.device, compute_type=self.compute_type
        )
        log.info("whisper loaded: %s (%s/%s)",
                 self.model_size, self.device, self.compute_type)

    def transcribe_sync(self, audio: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("WhisperSTT.load() has not been called")
        segments, _ = self._model.transcribe(
            audio,
            language="en",
            beam_size=self.beam_size,
            vad_filter=self.vad_filter,
        )
        return " ".join(seg.text.strip() for seg in segments).strip()


class UtteranceRecorder:
    def __init__(self, router: MicRouter, sample_rate: int = 16000,
                 speech_rms_threshold: int = 500, silence_ms: int = 700,
                 max_utterance_s: int = 30,
                 level_cb=None, abort_check=None) -> None:
        self._router = router
        self._sr = sample_rate
        self._speech_rms = speech_rms_threshold
        self._silence_frames = max(1, silence_ms // 80)
        self._max_frames = int(max_utterance_s * sample_rate / 1280)
        self._level_cb = level_cb
        self._abort_check = abort_check

    async def record(self, timeout_s: float) -> Optional[np.ndarray]:
        deadline = time.monotonic() + timeout_s
        frames: list[np.ndarray] = []
        speaking = False
        silent_run = 0

        while time.monotonic() < deadline:
            if self._abort_check and self._abort_check():
                break
            try:
                frame = await asyncio.wait_for(
                    self._router.get_frame(),
                    timeout=max(0.05, min(0.2, deadline - time.monotonic())),
                )
            except asyncio.TimeoutError:
                continue

            energy = rms(frame)
            if self._level_cb:
                self._level_cb(min(1.0, energy / 4000.0))

            if not speaking:
                if energy >= self._speech_rms:
                    speaking = True
                    frames.append(frame)
            else:
                frames.append(frame)
                silent_run = silent_run + 1 if energy < self._speech_rms else 0
                if silent_run >= self._silence_frames:
                    break
                if len(frames) >= self._max_frames:
                    break

        if not speaking or len(frames) < 4:
            return None
        pcm = np.concatenate(frames).astype(np.float32) / 32768.0
        return pcm
