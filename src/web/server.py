from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.audio.devices import list_input_devices, list_output_devices
from src.audio.pipeline import AtomPipeline
from src.core.config import AppConfig
from src.core.state import StateBus
from src.core.telemetry import TelemetrySampler

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


class ChatInput(BaseModel):
    text: str


class DeviceSelection(BaseModel):
    input_device: str | None = None
    output_device: str | None = None


class WorkspaceInput(BaseModel):
    workspace: str


def create_app(cfg: AppConfig, bus: StateBus, pipeline: AtomPipeline) -> FastAPI:
    app = FastAPI(title="A.T.O.M. Localhost HUD")
    sampler = TelemetrySampler(cfg.hw.vram_budget_mb)

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/api/snapshot")
    async def get_snapshot():
        snap = bus.snapshot()
        snap["workspace"] = str(pipeline.workspace)
        snap["tier"] = getattr(pipeline.brain, "last_tier", "Standby")
        snap["telemetry"] = sampler.sample().to_dict()
        return snap

    @app.get("/api/devices")
    async def get_devices():
        return {
            "inputs": ["Default"] + list_input_devices(),
            "outputs": ["Default"] + list_output_devices(),
            "current_input": cfg.audio.input_device or "Default",
            "current_output": cfg.audio.output_device or "Default",
        }

    @app.post("/api/devices")
    async def update_devices(sel: DeviceSelection):
        in_dev = None if sel.input_device in (None, "", "Default") else sel.input_device
        out_dev = None if sel.output_device in (None, "", "Default") else sel.output_device
        pipeline.set_input_device(in_dev)
        pipeline.set_output_device(out_dev)
        return {"ok": True}

    @app.post("/api/wake")
    async def wake_atom():
        pipeline.trigger_wake()
        return {"ok": True}

    @app.post("/api/stand_down")
    async def stand_down():
        pipeline.trigger_stand_down()
        return {"ok": True}

    @app.post("/api/clear_memory")
    async def clear_memory():
        pipeline.clear_memory()
        return {"ok": True}

    @app.post("/api/chat")
    async def send_chat(body: ChatInput):
        pipeline.submit_text_query(body.text)
        return {"ok": True}

    @app.post("/api/workspace")
    async def update_workspace(body: WorkspaceInput):
        pipeline.set_workspace(body.workspace)
        return {"ok": True, "workspace": str(pipeline.workspace)}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        # Send initial state snapshot immediately on connect
        init_snap = bus.snapshot()
        init_snap["workspace"] = str(pipeline.workspace)
        init_snap["tier"] = getattr(pipeline.brain, "last_tier", "Standby")
        init_snap["telemetry"] = sampler.sample().to_dict()
        await ws.send_json({"kind": "init", "value": init_snap})

        last_telemetry = 0.0
        try:
            while True:
                for msg in bus.drain():
                    await ws.send_json({"kind": msg.kind, "value": msg.value})

                now = asyncio.get_running_loop().time()
                if now - last_telemetry >= cfg.hw.telemetry_interval_s:
                    last_telemetry = now
                    await ws.send_json({
                        "kind": "telemetry",
                        "value": sampler.sample().to_dict(),
                        "tier": getattr(pipeline.brain, "last_tier", "Standby"),
                    })
                await asyncio.sleep(0.04)  # ~25 Hz real-time push
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            log.debug("WebSocket closed: %s", exc)

    return app
