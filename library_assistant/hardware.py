"""Hardware detection module for the Library Assistant.

This module provides pure parsers for various hardware information sources
and a detection runner that collects them into a HardwareReport.
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HardwareReport:
    """Represents the hardware information collected from the system."""

    platform: str
    ram_gb: float
    accelerators: list[dict[str, str | float]]
    pool_gb: float
    pool_source: str
    problems: list[str]


def parse_meminfo(text: str) -> dict[str, float]:
    """Parse /proc/meminfo content and return memory information in GB."""
    result = {}
    for line in text.splitlines():
        if line.startswith("MemTotal:"):
            # Memory is in KB, convert to GB
            result["total"] = int(line.split()[1]) / (1024 * 1024)
        elif line.startswith("MemAvailable:"):
            # Memory is in KB, convert to GB
            result["available"] = int(line.split()[1]) / (1024 * 1024)
    return result


def parse_nvidia_smi_csv(text: str) -> list[dict[str, float | str]]:
    """Parse nvidia-smi --query-gpu=... CSV output.

    Returns a list of dictionaries, one per GPU.
    """
    if not text.strip():
        return []

    lines = text.strip().split("\n")
    if len(lines) < 2:
        return []

    # First line contains headers
    headers = [h.strip() for h in lines[0].split(",")]

    result = []
    for line in lines[1:]:
        if not line.strip():
            continue

        values = [v.strip() for v in line.split(",")]
        if len(values) != len(headers):
            continue

        gpu_data = {}
        for header, value in zip(headers, values):
            # Convert numeric values to appropriate types
            if header in ("memory.total", "memory.free", "memory.used"):
                try:
                    gpu_data[header] = float(value)
                except ValueError:
                    gpu_data[header] = 0.0
            else:
                gpu_data[header] = value

        result.append(gpu_data)

    return result


def parse_amdgpu_sysfs(path: Path) -> dict[str, float] | None:
    """Read VRAM information from AMDGPU sysfs.

    Returns None if the sysfs path is not readable or doesn't contain the expected files.
    """
    try:
        # Try to read the mem_info_vram_total file
        total_path = path / "mem_info_vram_total"
        used_path = path / "mem_info_vram_used"

        if not total_path.exists():
            return None

        total = int(total_path.read_text().strip()) / (1024**3)  # Convert bytes to GB

        # Read used memory if available
        used = 0.0
        if used_path.exists():
            used = int(used_path.read_text().strip()) / (1024**3)  # Convert bytes to GB

        return {
            "total": total,
            "used": used,
        }
    except (OSError, ValueError):
        return None


def parse_sysctl_memsize(text: str) -> float:
    """Parse the byte count printed by `sysctl -n hw.memsize` into GB."""
    return int(text.strip()) / (1024**3)


def detect_amd_gpus(drm: Path = Path("/sys/class/drm")) -> list[dict]:
    """AMD GPUs under `drm`. A card's vendor and VRAM files are in its device folder."""
    gpus: list[dict] = []
    try:
        for card_dir in drm.glob("card*"):
            device = card_dir / "device"
            if (device / "vendor").exists():
                try:
                    vendor_id = (device / "vendor").read_text().strip()
                    # AMD vendor ID is 0x1002
                    if vendor_id.startswith("0x1002") or vendor_id == "1002":
                        amdgpu_info = parse_amdgpu_sysfs(device)
                        if amdgpu_info:
                            gpus.append(
                                {
                                    "type": "amd",
                                    "name": card_dir.name,
                                    "memory_gb": amdgpu_info["total"],
                                    "status": "ok",
                                    "stderr": None,
                                }
                            )
                except (OSError, ValueError):
                    pass
    except (OSError, ValueError):
        pass
    return gpus


def detect() -> HardwareReport:
    """Detect hardware configuration and return a HardwareReport.

    This function makes no network calls and only spawns nvidia-smi and sysctl.
    """
    # Determine platform
    platform = sys.platform

    # Get RAM information from /proc/meminfo (Linux) or sysctl (macOS)
    ram_gb = 0.0
    problems = []

    if platform == "darwin":
        # macOS
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=True,
            )
            ram_gb = parse_sysctl_memsize(result.stdout)
        except (OSError, subprocess.CalledProcessError, ValueError):
            ram_gb = 8.0  # Default fallback
            problems.append("Failed to determine RAM on macOS")
    else:
        # Linux and other Unix systems
        try:
            with open("/proc/meminfo", "r") as f:
                meminfo_text = f.read()
            meminfo = parse_meminfo(meminfo_text)
            ram_gb = meminfo.get("total", 0.0)
        except (OSError, ValueError):
            ram_gb = 8.0  # Default fallback
            problems.append("Failed to determine RAM from /proc/meminfo")

    # Initialize accelerators list
    accelerators = []

    # Detect NVIDIA GPUs. A missing binary means no entry (no GPU); a binary
    # that exists but exits non-zero (e.g. WSL's missing libnvidia-ml.so)
    # must still produce an accelerator entry, marked failed with its stderr.
    try:
        nvidia_result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        nvidia_result = None

    if nvidia_result is not None:
        if nvidia_result.returncode == 0:
            for gpu in parse_nvidia_smi_csv(nvidia_result.stdout):
                memory_mib = gpu.get("memory.total", 0.0)
                accelerators.append(
                    {
                        "type": "nvidia",
                        "name": gpu.get("name", "Unknown"),
                        "memory_gb": memory_mib / 1024,  # memory.total is MiB
                        "status": "ok",
                        "stderr": None,
                    }
                )
        else:
            accelerators.append(
                {
                    "type": "nvidia",
                    "name": "Unknown",
                    "memory_gb": 0.0,
                    "status": "failed",
                    "stderr": nvidia_result.stderr.strip()
                    if nvidia_result.stderr
                    else "",
                }
            )

    accelerators.extend(detect_amd_gpus())

    # Determine pool size
    pool_gb = ram_gb  # Default to RAM if no accelerators
    pool_source = "ram"

    # If we have accelerators, use their memory for the pool
    if accelerators:
        total_accelerator_memory = sum(
            acc["memory_gb"] for acc in accelerators if acc["status"] == "ok"
        )
        if total_accelerator_memory > 0:
            pool_gb = total_accelerator_memory
            pool_source = "accelerator_memory"

    # Return the HardwareReport
    return HardwareReport(
        platform=platform,
        ram_gb=ram_gb,
        accelerators=accelerators,
        pool_gb=pool_gb,
        pool_source=pool_source,
        problems=problems,
    )
