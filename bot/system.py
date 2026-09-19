from __future__ import annotations

import ctypes
import os
import platform
import shutil
import sys
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path


_STARTED_AT = time.monotonic()


@dataclass(frozen=True)
class SystemStats:
    hostname: str
    os_name: str
    os_release: str
    architecture: str
    cpu_name: str
    cpu_count: int
    cpu_percent: float | None
    threads: int
    ram_total: int | None
    ram_available: int | None
    process_ram: int | None
    disk_total: int
    disk_used: int
    disk_free: int
    load_average: tuple[float, float, float] | None
    python_version: str
    pid: int


def _cpu_name() -> str:
    name = platform.processor().strip()
    if name:
        return name

    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        try:
            for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass

    return platform.machine() or "N/A"


def _linux_cpu_times() -> tuple[int, int] | None:
    path = Path("/proc/stat")
    if not path.is_file():
        return None

    try:
        values = [int(value) for value in path.read_text().splitlines()[0].split()[1:]]
    except (OSError, ValueError, IndexError):
        return None

    if len(values) < 4:
        return None

    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


def _windows_cpu_times() -> tuple[int, int] | None:
    class FileTime(ctypes.Structure):
        _fields_ = [
            ("low", wintypes.DWORD),
            ("high", wintypes.DWORD),
        ]

    idle = FileTime()
    kernel = FileTime()
    user = FileTime()

    if not ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        return None

    def value(item: FileTime) -> int:
        return (item.high << 32) | item.low

    idle_value = value(idle)
    total = value(kernel) + value(user)
    return idle_value, total


def _cpu_percent() -> float | None:
    reader = _windows_cpu_times if os.name == "nt" else _linux_cpu_times
    first = reader()
    if first is None:
        return None

    time.sleep(0.12)
    second = reader()
    if second is None:
        return None

    idle_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    if total_delta <= 0:
        return None

    value = 100.0 * (1.0 - idle_delta / total_delta)
    return max(0.0, min(100.0, value))


def _memory() -> tuple[int | None, int | None]:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.DWORD),
                ("memory_load", wintypes.DWORD),
                ("total_phys", ctypes.c_ulonglong),
                ("avail_phys", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("avail_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("avail_virtual", ctypes.c_ulonglong),
                ("avail_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total_phys, status.avail_phys
        return None, None

    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        available_pages = os.sysconf("SC_AVPHYS_PAGES")
        return total_pages * page_size, available_pages * page_size
    except (AttributeError, OSError, ValueError):
        return None, None


def _process_memory() -> int | None:
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("page_fault_count", wintypes.DWORD),
                ("peak_working_set_size", ctypes.c_size_t),
                ("working_set_size", ctypes.c_size_t),
                ("quota_peak_paged_pool_usage", ctypes.c_size_t),
                ("quota_paged_pool_usage", ctypes.c_size_t),
                ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
                ("quota_non_paged_pool_usage", ctypes.c_size_t),
                ("pagefile_usage", ctypes.c_size_t),
                ("peak_pagefile_usage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()

        if ctypes.windll.psapi.GetProcessMemoryInfo(
            process,
            ctypes.byref(counters),
            counters.cb,
        ):
            return counters.working_set_size
        return None

    statm = Path("/proc/self/statm")
    if statm.is_file():
        try:
            resident_pages = int(statm.read_text().split()[1])
            return resident_pages * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            pass

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return usage if sys.platform == "darwin" else usage * 1024
    except (ImportError, AttributeError):
        return None


def read_system_stats() -> SystemStats:
    root = Path.cwd().anchor or "/"
    disk = shutil.disk_usage(root)

    try:
        load_average = os.getloadavg()
    except (AttributeError, OSError):
        load_average = None

    ram_total, ram_available = _memory()

    return SystemStats(
        hostname=platform.node() or "N/A",
        os_name=platform.system() or "N/A",
        os_release=platform.release() or "N/A",
        architecture=platform.machine() or "N/A",
        cpu_name=_cpu_name(),
        cpu_count=os.cpu_count() or 0,
        cpu_percent=_cpu_percent(),
        threads=threading.active_count(),
        ram_total=ram_total,
        ram_available=ram_available,
        process_ram=_process_memory(),
        disk_total=disk.total,
        disk_used=disk.used,
        disk_free=disk.free,
        load_average=load_average,
        python_version=platform.python_version(),
        pid=os.getpid(),
    )


def process_uptime() -> float:
    return max(0.0, time.monotonic() - _STARTED_AT)


def format_bytes(value: int | None) -> str:
    if value is None:
        return "N/A"

    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def format_duration(seconds: float) -> str:
    total = int(seconds)
    days, total = divmod(total, 86400)
    hours, total = divmod(total, 3600)
    minutes, secs = divmod(total, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)
