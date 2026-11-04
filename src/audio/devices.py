from __future__ import annotations
import sounddevice as sd


def list_input_devices() -> list[str]:
    seen = set()
    out = []
    for dev in sd.query_devices():
        if dev["max_input_channels"] > 0 and dev["name"] not in seen:
            seen.add(dev["name"])
            out.append(dev["name"])
    return out


def list_output_devices() -> list[str]:
    seen = set()
    out = []
    for dev in sd.query_devices():
        if dev["max_output_channels"] > 0 and dev["name"] not in seen:
            seen.add(dev["name"])
            out.append(dev["name"])
    return out
