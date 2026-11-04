from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from src.core.config import AppConfig, load_config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are A.T.O.M., a sharp, concise autonomous desktop AI assistant running on Windows 11. "
    "Because your replies are spoken aloud via text-to-speech, keep conversational responses natural, "
    "direct, and under 2-3 short sentences unless asked for code or detail. "
    "If the user asks you to write or save a code file, include a line 'FILE: filename.ext' followed "
    "by a fenced code block and a one-sentence spoken summary."
)

_SKIP_TOKENS = ("whisper", "tts", "guard", "orpheus", "playai", "embed", "allam", "safeguard")


class Brain(Protocol):
    last_tier: str
    async def respond(self, text: str) -> str: ...
    def clear_context(self) -> None: ...


class RouterBrain:
    """Three-tier LLM cascade: Tier 1 Groq -> Tier 2 NVIDIA NIM -> Tier 3 Local Ollama."""

    def __init__(self, cfg: AppConfig | None = None) -> None:
        self.cfg = cfg or load_config()
        self._history: list[dict[str, str]] = []
        self.last_tier: str = "Standby"

    def _messages(self, user_text: str) -> list[dict[str, str]]:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        msgs.extend(self._history[-10:])
        msgs.append({"role": "user", "content": user_text})
        return msgs

    def _call_groq(self, messages: list[dict[str, str]]) -> str:
        from groq import Groq, NotFoundError
        client = Groq(api_key=self.cfg.groq_api_key, timeout=self.cfg.llm.request_timeout_s)
        try:
            resp = client.chat.completions.create(
                model=self.cfg.llm.groq_model,
                messages=messages,
                temperature=0.6,
                max_tokens=600,
            )
            return (resp.choices[0].message.content or "").strip()
        except NotFoundError:
            models = [
                m.id for m in client.models.list().data
                if not any(tok in m.id.lower() for tok in _SKIP_TOKENS)
            ]
            if not models:
                raise
            preferred = [
                m for m in models
                if any(k in m.lower() for k in ("llama", "qwen", "deepseek", "mixtral", "gemma", "gpt"))
            ]
            chosen = preferred[0] if preferred else models[0]
            log.info("Groq auto-selected model: %s", chosen)
            self.cfg.llm.groq_model = chosen
            resp = client.chat.completions.create(
                model=chosen,
                messages=messages,
                temperature=0.6,
                max_tokens=600,
            )
            return (resp.choices[0].message.content or "").strip()

    def _call_nvidia(self, messages: list[dict[str, str]]) -> str:
        from openai import OpenAI
        client = OpenAI(
            base_url=self.cfg.llm.nvidia_base_url,
            api_key=self.cfg.nvidia_api_key,
            timeout=self.cfg.llm.request_timeout_s,
        )
        resp = client.chat.completions.create(
            model=self.cfg.llm.nvidia_model,
            messages=messages,
            temperature=0.6,
            max_tokens=600,
        )
        return (resp.choices[0].message.content or "").strip()

    def _call_ollama(self, messages: list[dict[str, str]]) -> str:
        import ollama
        try:
            resp = ollama.chat(
                model=self.cfg.llm.ollama_model,
                messages=messages,
                options={"num_gpu": self.cfg.llm.ollama_num_gpu_layers},
            )
            return resp["message"]["content"].strip()
        except Exception as exc:
            if "not found" not in str(exc).lower():
                raise
            models_resp = ollama.list()
            raw_models = getattr(models_resp, "models", None) or models_resp.get("models", [])
            available = [
                getattr(m, "model", None) or getattr(m, "name", None) or m.get("model") or m.get("name")
                for m in raw_models
            ]
            available = [m for m in available if m and "embed" not in m.lower()]
            if not available:
                raise RuntimeError("No local Ollama models installed.") from exc
            chosen = available[0]
            self.cfg.llm.ollama_model = chosen
            resp = ollama.chat(
                model=chosen,
                messages=messages,
                options={"num_gpu": self.cfg.llm.ollama_num_gpu_layers},
            )
            return resp["message"]["content"].strip()

    async def respond(self, text: str) -> str:
        loop = asyncio.get_running_loop()
        messages = self._messages(text)
        reply = ""

        if self.cfg.groq_api_key:
            try:
                reply = await loop.run_in_executor(None, self._call_groq, messages)
                self.last_tier = f"Tier 1 · Groq ({self.cfg.llm.groq_model})"
            except Exception as exc:
                log.warning("Tier 1 (Groq) failed: %s", exc)

        if not reply and self.cfg.nvidia_api_key:
            try:
                reply = await loop.run_in_executor(None, self._call_nvidia, messages)
                self.last_tier = f"Tier 2 · NVIDIA ({self.cfg.llm.nvidia_model})"
            except Exception as exc:
                log.warning("Tier 2 (NVIDIA) failed: %s", exc)

        if not reply:
            try:
                reply = await loop.run_in_executor(None, self._call_ollama, messages)
                self.last_tier = f"Tier 3 · Ollama ({self.cfg.llm.ollama_model})"
            except Exception as exc:
                log.warning("Tier 3 (Ollama) failed: %s", exc)

        if not reply:
            self.last_tier = "Unconfigured"
            return (
                "No language model responded. Add a Groq or NVIDIA API key in your .env file, "
                "or start Ollama with a local model."
            )

        self._history.append({"role": "user", "content": text})
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def clear_context(self) -> None:
        self._history.clear()
