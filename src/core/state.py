from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from enum import Enum


class AtomState(str, Enum):
    BOOTING = "booting"
    STANDBY = "standby"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    OFFLINE = "offline"


@dataclass
class BusMessage:
    kind: str  # "state" | "status" | "level" | "online" | "chat" | "log"
    value: object
    ts: float = field(default_factory=time.time)


class StateBus:
    """Thread-safe pub/sub state bridge between the voice/LLM engine and WebSocket clients."""

    def __init__(self) -> None:
        self._q: "queue.Queue[BusMessage]" = queue.Queue()
        self._lock = threading.Lock()
        self._state = AtomState.BOOTING
        self._online = True
        self._status = "Booting ATOM core..."
        self._level = 0.0
        self._chat_history: list[dict] = []

    def _push(self, kind: str, value: object) -> None:
        self._q.put(BusMessage(kind, value))

    def set_state(self, state: AtomState) -> None:
        with self._lock:
            self._state = state
        self._push("state", state.value)

    def set_online(self, online: bool) -> None:
        with self._lock:
            self._online = online
        self._push("online", online)

    def status(self, text: str) -> None:
        with self._lock:
            self._status = text
        self._push("status", text)

    def level(self, value: float) -> None:
        clamped = max(0.0, min(1.0, float(value)))
        with self._lock:
            self._level = clamped
        self._push("level", round(clamped, 3))

    def chat(self, role: str, text: str, tier: str = "") -> None:
        entry = {"role": role, "text": text, "tier": tier, "ts": time.strftime("%H:%M:%S")}
        with self._lock:
            self._chat_history.append(entry)
            self._chat_history = self._chat_history[-50:]
        self._push("chat", entry)

    def drain(self) -> list[BusMessage]:
        out: list[BusMessage] = []
        while True:
            try:
                out.append(self._q.get_nowait())
            except queue.Empty:
                return out

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state.value,
                "online": self._online,
                "status": self._status,
                "level": self._level,
                "chat_history": list(self._chat_history),
            }

    @property
    def state(self) -> AtomState:
        with self._lock:
            return self._state

    @property
    def online(self) -> bool:
        with self._lock:
            return self._online
