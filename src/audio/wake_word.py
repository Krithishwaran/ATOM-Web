from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


class WakeWordEngine:
    def __init__(
        self,
        model_path: Optional[Path],
        fallback_model: str = "hey_jarvis",
        threshold: float = 0.5,
        inference_framework: str = "onnx",
    ) -> None:
        import openwakeword.utils
        from openwakeword.model import Model

        self.threshold = threshold
        if model_path and Path(model_path).exists():
            self._model = Model(
                wakeword_models=[str(model_path)],
                inference_framework=inference_framework,
            )
            self.target_name = Path(model_path).stem
            log.info("custom wake model loaded: %s", model_path)
        else:
            try:
                self._model = Model(
                    wakeword_models=[fallback_model],
                    inference_framework=inference_framework,
                )
            except Exception:
                log.info("Downloading missing openWakeWord resource models...")
                openwakeword.utils.download_models()
                self._model = Model(
                    wakeword_models=[fallback_model],
                    inference_framework=inference_framework,
                )
            self.target_name = fallback_model
            log.warning(
                "no custom wake model found - using built-in '%s' as stand-in "
                "for 'wake up atom'",
                fallback_model,
            )

    def score(self, frame: np.ndarray) -> float:
        prediction = self._model.predict(frame)
        return float(prediction.get(self.target_name, 0.0))

    def detected(self, frame: np.ndarray) -> bool:
        if self.score(frame) >= self.threshold:
            self._model.reset()
            return True
        return False
