from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
import psutil

log = logging.getLogger(__name__)


@dataclass
class Telemetry:
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    gpu_percent: float = 0.0
    vram_used_mb: float = 0.0
    vram_total_mb: float = 0.0
    vram_budget_mb: int = 3072
    vram_over_budget: bool = False
    gpu_available: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class _NvmlBackend:
    name = "nvml"

    def __init__(self) -> None:
        import pynvml
        pynvml.nvmlInit()
        self._nv = pynvml
        self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)

    def read(self) -> tuple[float, float, float]:
        util = self._nv.nvmlDeviceGetUtilizationRates(self._handle)
        mem = self._nv.nvmlDeviceGetMemoryInfo(self._handle)
        return float(util.gpu), mem.used / 1e6, mem.total / 1e6

    def shutdown(self) -> None:
        try:
            self._nv.nvmlShutdown()
        except Exception:
            pass


class _GputilBackend:
    name = "GPUtil"

    def __init__(self) -> None:
        import GPUtil
        self._gp = GPUtil
        if not self._gp.getGPUs():
            raise RuntimeError("no GPU visible to GPUtil")

    def read(self) -> tuple[float, float, float]:
        gpu = self._gp.getGPUs()[0]
        return gpu.load * 100.0, gpu.memoryUsed, gpu.memoryTotal

    def shutdown(self) -> None:
        pass


class TelemetrySampler:
    def __init__(self, vram_budget_mb: int = 3072) -> None:
        self.vram_budget_mb = vram_budget_mb
        self._backend = None
        for backend in (_NvmlBackend, _GputilBackend):
            try:
                self._backend = backend()
                log.info("GPU telemetry backend: %s", backend.name)
                break
            except Exception as exc:
                log.debug("GPU backend %s unavailable: %s", backend.name, exc)
        psutil.cpu_percent(interval=None)

    def sample(self) -> Telemetry:
        t = Telemetry(vram_budget_mb=self.vram_budget_mb)
        t.cpu_percent = round(psutil.cpu_percent(interval=None), 1)
        vm = psutil.virtual_memory()
        t.ram_percent = round(vm.percent, 1)
        t.ram_used_gb = round(vm.used / 1e9, 2)
        t.ram_total_gb = round(vm.total / 1e9, 2)
        if self._backend is not None:
            try:
                gpu, used, total = self._backend.read()
                t.gpu_available = True
                t.gpu_percent = round(gpu, 1)
                t.vram_used_mb = round(used, 0)
                t.vram_total_mb = round(total, 0)
                t.vram_over_budget = used > self.vram_budget_mb
            except Exception as exc:
                log.debug("GPU sample failed: %s", exc)
        return t

    def shutdown(self) -> None:
        if self._backend is not None:
            self._backend.shutdown()
