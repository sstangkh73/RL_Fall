"""Capture a non-invasive machine/dependency snapshot before benchmark runs."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
from pathlib import Path

import gymnasium
import mujoco
import psutil
import stable_baselines3
import torch


def gpu_snapshot() -> list[dict[str, str]]:
    fields = ("name", "driver_version", "memory.total", "memory.free",
              "utilization.gpu", "temperature.gpu")
    try:
        output = subprocess.check_output(
            ["nvidia-smi", f"--query-gpu={','.join(fields)}", "--format=csv,noheader,nounits"],
            text=True, timeout=4, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return [dict(zip(fields, (value.strip() for value in line.split(","))))
                for line in output.strip().splitlines()]
    except (OSError, subprocess.SubprocessError):
        return []


def cpu_name() -> str | None:
    try:
        command = ["powershell", "-NoProfile", "-Command",
                   "(Get-ItemProperty -LiteralPath 'HKLM:\\HARDWARE\\DESCRIPTION\\System\\CentralProcessor\\0').ProcessorNameString"]
        return subprocess.check_output(command, text=True, timeout=4,
                                       creationflags=subprocess.CREATE_NO_WINDOW).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    path = Path("results/benchmark/system_snapshot.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    memory = psutil.virtual_memory()
    snapshot = {
        "captured_unix": time.time(), "cpu_name": cpu_name(),
        "logical_processors": os.cpu_count(), "system_ram_bytes": memory.total,
        "system_available_ram_bytes": memory.available,
        "platform": platform.platform(), "python": platform.python_version(),
        "dependencies": {
            "mujoco": mujoco.__version__, "gymnasium": gymnasium.__version__,
            "stable_baselines3": stable_baselines3.__version__,
            "torch": torch.__version__, "torch_cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(), "psutil": psutil.__version__,
        },
        "gpus": gpu_snapshot(),
        "policy": "No applications closed and no power plan changed by benchmark tooling.",
    }
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

