"""Low-frequency resource telemetry for benchmark runs."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path

import psutil

# CREATE_NO_WINDOW exists only on Windows; 0 is the POSIX no-op.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ResourceSampler:
    def __init__(self, output: Path, interval_seconds: float = 1.0) -> None:
        self.output = output
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.process = psutil.Process()

    def start(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval_seconds * 2 + 1)

    def _process_tree_rss(self) -> int:
        processes = [self.process] + self.process.children(recursive=True)
        total = 0
        for process in processes:
            try:
                total += process.memory_info().rss
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return total

    @staticmethod
    def _gpu() -> dict[str, float | None]:
        command = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,temperature.gpu,clocks.sm,power.draw",
            "--format=csv,noheader,nounits",
        ]
        try:
            output = subprocess.check_output(
                command, text=True, timeout=2, creationflags=NO_WINDOW
            ).strip().splitlines()[0]
            values = [value.strip() for value in output.split(",")]
            parsed = []
            for value in values:
                try:
                    parsed.append(float(value))
                except ValueError:
                    parsed.append(None)
            return dict(zip(("gpu_util_percent", "vram_used_mib", "gpu_temp_c",
                             "gpu_sm_clock_mhz", "gpu_power_w"), parsed))
        except (OSError, subprocess.SubprocessError, IndexError):
            return {key: None for key in ("gpu_util_percent", "vram_used_mib",
                                          "gpu_temp_c", "gpu_sm_clock_mhz", "gpu_power_w")}

    def _run(self) -> None:
        with self.output.open("a", encoding="utf-8") as stream:
            while not self._stop.is_set():
                memory = psutil.virtual_memory()
                record = {
                    "monotonic_seconds": time.perf_counter(),
                    "cpu_percent_system": psutil.cpu_percent(interval=None),
                    "system_available_bytes": memory.available,
                    # This can double-count shared pages; the report labels it accordingly.
                    "process_tree_rss_sum_bytes": self._process_tree_rss(),
                    **self._gpu(),
                }
                stream.write(json.dumps(record, sort_keys=True) + "\n")
                stream.flush()
                self._stop.wait(self.interval_seconds)

