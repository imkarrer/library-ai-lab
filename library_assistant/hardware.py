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

        total = int(total_path.read_text().strip()) / (1024 * 1024)  # Convert KB to GB

        # Read used memory if available
        used = 0.0
        if used_path.exists():
            used = int(used_path.read_text().strip()) / (
                1024 * 1024
            )  # Convert KB to GB

        return {
            "total": total,
            "used": used,
        }
    except (OSError, ValueError):
        return None


def get_macos_pool() -> tuple[float, str]:
    """Get the Metal pool size on macOS using ctypes.

    Returns a tuple of (pool_gb, source) where source indicates how the pool was determined.
    """
    try:
        import ctypes
        import ctypes.util

        # Try to load the Objective-C runtime and Metal framework
        try:
            # Load Foundation framework
            foundation = ctypes.util.find_library("Foundation")
            if foundation:
                ctypes.CDLL(foundation, mode=ctypes.RTLD_GLOBAL)

            # Load Metal framework
            metal = ctypes.util.find_library("Metal")
            if metal:
                ctypes.CDLL(metal, mode=ctypes.RTLD_GLOBAL)

            # Try to get recommendedMaxWorkingSetSize via ctypes
            # This is a simplified approach - in practice we'd need more complex Objective-C interop
            # For now, we'll fall back to sysctl for compatibility
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=True,
            )
            total_mem = int(result.stdout.strip()) / (
                1024 * 1024
            )  # Convert bytes to MB then GB
            return (total_mem, "hw.memsize fallback")

        except (OSError, subprocess.CalledProcessError):
            # If we can't get Metal info, fall back to sysctl
            try:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                total_mem = int(result.stdout.strip()) / (
                    1024 * 1024
                )  # Convert bytes to MB then GB
                return (
                    total_mem * 0.7,
                    "estimated from hw.memsize",
                )  # Conservative estimate
            except (OSError, subprocess.CalledProcessError):
                # If everything fails, return a default
                return (8.0, "default fallback")

    except ImportError:
        # If ctypes is not available, fall back to sysctl
        try:
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
                check=True,
            )
            total_mem = int(result.stdout.strip()) / (
                1024 * 1024
            )  # Convert bytes to MB then GB
            return (total_mem * 0.7, "estimated from hw.memsize fallback")
        except (OSError, subprocess.CalledProcessError):
            return (8.0, "default fallback")


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
            ram_gb = int(result.stdout.strip()) / (1024 * 1024)  # Convert bytes to GB
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

    # Detect NVIDIA GPUs
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        nvidia_data = parse_nvidia_smi_csv(result.stdout)
        for gpu in nvidia_data:
            accelerators.append(
                {
                    "type": "nvidia",
                    "name": gpu.get("name", "Unknown"),
                    "memory_gb": gpu.get("memory.total", 0.0),
                    "status": "ok",
                    "stderr": None,
                }
            )
    except (OSError, subprocess.CalledProcessError):
        # NVIDIA detection failed - this is expected on non-NVIDIA systems
        # If nvidia-smi exists but fails, mark it as failed
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, check=True)
            # If nvidia-smi exists but failed, mark it as failed
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,memory.total,memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,  # This is expected to fail
                )
                if result.stderr:
                    accelerators.append(
                        {
                            "type": "nvidia",
                            "name": "Unknown",
                            "memory_gb": 0.0,
                            "status": "failed",
                            "stderr": result.stderr.strip(),
                        }
                    )
            except (OSError, subprocess.CalledProcessError):
                pass
        except (OSError, subprocess.CalledProcessError):
            # nvidia-smi not available, which is fine
            pass

    # Detect AMD GPUs via sysfs
    try:
        # Look for AMDGPU devices
        for card_dir in Path("/sys/class/drm").glob("card*"):
            if (card_dir / "device" / "vendor").exists():
                try:
                    vendor_id = (card_dir / "device" / "vendor").read_text().strip()
                    # AMD vendor ID is 0x1002
                    if vendor_id.startswith("0x1002") or vendor_id == "1002":
                        amdgpu_info = parse_amdgpu_sysfs(card_dir)
                        if amdgpu_info:
                            accelerators.append(
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

    # On macOS, try to get the Metal pool
    if platform == "darwin":
        try:
            metal_pool, source = get_macos_pool()
            pool_gb = metal_pool
            pool_source = source
        except (OSError, subprocess.CalledProcessError):
            pass

    # Return the HardwareReport
    return HardwareReport(
        platform=platform,
        ram_gb=ram_gb,
        accelerators=accelerators,
        pool_gb=pool_gb,
        pool_source=pool_source,
        problems=problems,
    )
