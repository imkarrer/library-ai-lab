"""Tests for the hardware detection module."""

import subprocess
from pathlib import Path

import pytest

from library_assistant import hardware
from library_assistant.hardware import (
    HardwareReport,
    detect,
    detect_amd_gpus,
    parse_amdgpu_sysfs,
    parse_meminfo,
    parse_nvidia_smi_csv,
    parse_sysctl_memsize,
)


def test_parse_meminfo():
    """Test parsing /proc/meminfo content."""
    meminfo_text = """MemTotal:        8123456 kB
MemAvailable:    6543210 kB
MemFree:         1234567 kB
"""
    result = parse_meminfo(meminfo_text)
    # Use approximate equality due to floating point precision
    assert abs(result["total"] - 7.74713134765625) < 0.001
    assert abs(result["available"] - 6.240234375) < 0.001


def test_parse_nvidia_smi_csv_single_card():
    """Test parsing nvidia-smi CSV output for a single card."""
    nvidia_text = """name,memory.total,memory.free
GeForce RTX 4080,16384,15000
"""
    result = parse_nvidia_smi_csv(nvidia_text)
    assert len(result) == 1
    assert result[0]["name"] == "GeForce RTX 4080"
    assert result[0]["memory.total"] == 16384.0
    assert result[0]["memory.free"] == 15000.0


def test_parse_nvidia_smi_csv_two_cards():
    """Test parsing nvidia-smi CSV output for two cards."""
    nvidia_text = """name,memory.total,memory.free
GeForce RTX 4080,16384,15000
GeForce RTX 4090,24576,23000
"""
    result = parse_nvidia_smi_csv(nvidia_text)
    assert len(result) == 2
    assert result[0]["name"] == "GeForce RTX 4080"
    assert result[0]["memory.total"] == 16384.0
    assert result[1]["name"] == "GeForce RTX 4090"
    assert result[1]["memory.total"] == 24576.0


def test_parse_nvidia_smi_csv_empty():
    """Test parsing empty nvidia-smi CSV output."""
    result = parse_nvidia_smi_csv("")
    assert result == []


def test_parse_nvidia_smi_csv_invalid():
    """Test parsing invalid nvidia-smi CSV output."""
    nvidia_text = """name,memory.total,memory.free
GeForce RTX 4080,invalid,15000
"""
    result = parse_nvidia_smi_csv(nvidia_text)
    # Should handle invalid numeric values gracefully
    assert len(result) == 1
    assert result[0]["memory.total"] == 0.0  # Invalid value converted to 0.0


def test_parse_amdgpu_sysfs_missing():
    """A sysfs path without the expected files yields None."""
    result = parse_amdgpu_sysfs(Path("/nonexistent"))
    assert result is None


def test_parse_amdgpu_sysfs_success(tmp_path):
    """Parsing a real AMDGPU sysfs fixture converts bytes to GB."""
    (tmp_path / "mem_info_vram_total").write_text("17179869184\n")  # 16 GiB
    (tmp_path / "mem_info_vram_used").write_text("1073741824\n")  # 1 GiB
    result = parse_amdgpu_sysfs(tmp_path)
    assert result is not None
    assert abs(result["total"] - 16.0) < 0.001
    assert abs(result["used"] - 1.0) < 0.001


def test_an_amd_card_is_found_from_the_real_sysfs_layout(tmp_path):
    """The kernel keeps vendor and VRAM files in cardN/device/, and lists the card's
    connectors beside it. A flat fixture once hid that detection looked one level up."""
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "mem_info_vram_total").write_text("17179869184\n")
    (tmp_path / "card0-HDMI-A-1").mkdir()
    [gpu] = detect_amd_gpus(tmp_path)
    assert (gpu["type"], gpu["name"]) == ("amd", "card0")
    assert abs(gpu["memory_gb"] - 16.0) < 0.001


def test_another_vendors_card_is_not_taken_for_amd(tmp_path):
    device = tmp_path / "card0" / "device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x10de\n")
    (device / "mem_info_vram_total").write_text("17179869184\n")
    assert detect_amd_gpus(tmp_path) == []


def test_parse_sysctl_memsize():
    """Parsing sysctl's byte count yields GB."""
    result = parse_sysctl_memsize("17179869184\n")
    assert abs(result - 16.0) < 0.001


def test_detect_reports_failed_not_absent_for_errored_tool(monkeypatch):
    """A tool that exists but errors (WSL's missing libnvidia-ml.so) yields
    a 'failed' accelerator with stderr, never silent absence."""

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "nvidia-smi"
        return subprocess.CompletedProcess(
            cmd,
            returncode=9,
            stdout="",
            stderr=("NVIDIA-SMI has failed because it couldn't find libnvidia-ml.so\n"),
        )

    monkeypatch.setattr(hardware.subprocess, "run", fake_run)
    report = detect()
    nvidia_accelerators = [a for a in report.accelerators if a["type"] == "nvidia"]
    assert len(nvidia_accelerators) == 1
    assert nvidia_accelerators[0]["status"] == "failed"
    assert "libnvidia-ml.so" in nvidia_accelerators[0]["stderr"]


def test_detect_only_spawns_nvidia_smi_and_sysctl(monkeypatch):
    """The runner spawns no subprocess other than nvidia-smi and sysctl."""
    real_run = subprocess.run
    spawned = []

    def spy_run(cmd, *args, **kwargs):
        spawned.append(cmd[0])
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(hardware.subprocess, "run", spy_run)
    detect()
    assert set(spawned) <= {"nvidia-smi", "sysctl"}


def test_hardware_report_dataclass():
    """Test that HardwareReport dataclass works correctly."""
    report = HardwareReport(
        platform="linux",
        ram_gb=16.0,
        accelerators=[],
        pool_gb=16.0,
        pool_source="ram",
        problems=[],
    )
    assert report.platform == "linux"
    assert report.ram_gb == 16.0
    assert report.accelerators == []
    assert report.pool_gb == 16.0
    assert report.pool_source == "ram"
    assert report.problems == []


if __name__ == "__main__":
    pytest.main([__file__])
