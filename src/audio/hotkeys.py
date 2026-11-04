from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)


class HotkeyTrigger:
    def __init__(self, combo: str = "ctrl+shift+space") -> None:
        self.combo = combo
        self.event = threading.Event()
        self._registered = False

    def trigger(self) -> None:
        """Can be triggered by physical hotkey OR the localhost web UI button."""
        self.event.set()

    def register(self) -> None:
        try:
            import keyboard
            keyboard.add_hotkey(self.combo, self.event.set)
            self._registered = True
            log.info("global hotkey armed: %s", self.combo)
        except Exception as exc:
            log.warning("hotkey registration failed (%s) - wake word & web button still work", exc)

    def unregister(self) -> None:
        if self._registered:
            try:
                import keyboard
                keyboard.unhook_all_hotkeys()
            except Exception:
                pass
            self._registered = False

    def consume(self) -> bool:
        if self.event.is_set():
            self.event.clear()
            return True
        return False
