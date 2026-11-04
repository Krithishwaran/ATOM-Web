from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class MicRouter:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        sample_rate: int = 16000,
        blocksize: int = 1280,
        device: Optional[str] = None,
    ) -> None:
        self._loop = loop
        self._sample_rate = sample_rate
        self._blocksize = blocksize
        self._device = device
        self._queue: "asyncio.Queue[np.ndarray]" = asyncio.Queue(maxsize=256)
        self._stream: Optional[sd.InputStream] = None
        self._restart = asyncio.Event()

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.debug("mic status: %s", status)
        frame = indata[:, 0].copy()
        try:
            self._loop.call_soon_threadsafe(self._enqueue, frame)
        except RuntimeError:
            pass

    def _enqueue(self, frame: np.ndarray) -> None:
        if self._queue.full():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._queue.put_nowait(frame)

    def start(self) -> None:
        self._open_stream(self._device)

    def _open_stream(self, device: Optional[str]) -> None:
        self.stop()
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self._blocksize,
            device=device,
            callback=self._callback,
        )
        self._stream.start()
        self._device = device
        log.info("mic stream open (device=%s)", device or "default")

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def request_device_change(self, device: Optional[str]) -> None:
        self._pending_device = device
        self._restart.set()

    async def maybe_restart(self) -> None:
        if self._restart.is_set():
            self._restart.clear()
            device = getattr(self, "_pending_device", None)
            await self._loop.run_in_executor(None, self._open_stream, device)

    async def get_frame(self) -> np.ndarray:
        return await self._queue.get()

    def flush(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return


def rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
