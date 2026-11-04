# AeroFlowSim - open-source CFD for nozzle aerodynamics and propulsion
# Copyright (C) 2026 Dhanwin Mehta
# SPDX-License-Identifier: GPL-3.0-or-later

"""How the 2D solver computes: which kernels (Numba or plain NumPy) and how many CPU threads.

Two settings, one place, used by the GUI's helper process, the command line and scripts alike:

    backend   "auto" (default): the Numba kernels if Numba can be imported, else NumPy;
              "numpy": always the NumPy reference implementation (tests compare the two);
              "numba": the Numba kernels (falls back to NumPy, with a note, if Numba is missing).
    threads   CPU threads of the Numba kernels; None = the default (physical cores minus one, at most
              MAX_DEFAULT_THREADS, because the residual is limited by memory bandwidth beyond that).

The environment variables AEROFLOWSIM_BACKEND and AEROFLOWSIM_THREADS set the start values (handy for
tests and CI). Nothing here imports Numba: aeroflowsim/euler/kernels.py does, the first time a solver needs it.
"""

import os
import sys

AUTO, NUMPY, NUMBA = "auto", "numpy", "numba"
BACKENDS = (AUTO, NUMPY, NUMBA)
MAX_DEFAULT_THREADS = 16     # more threads than this rarely help a memory-bound residual

_settings = {"backend": os.environ.get("AEROFLOWSIM_BACKEND", AUTO).lower(),
             "threads": int(os.environ["AEROFLOWSIM_THREADS"]) if os.environ.get("AEROFLOWSIM_THREADS") else None}


def physical_cores() -> int:
    """Number of physical CPU cores (logical processors without hyper-threading siblings); os.cpu_count() if unknown."""
    logical = os.cpu_count() or 1
    try:
        if sys.platform == "win32":
            return _windows_cores() or logical
        if sys.platform.startswith("linux"):
            pairs = set()
            phys = core = None
            with open("/proc/cpuinfo", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("physical id"):
                        phys = line.split(":")[1].strip()
                    elif line.startswith("core id"):
                        core = line.split(":")[1].strip()
                        pairs.add((phys, core))
            return len(pairs) or logical
        if sys.platform == "darwin":
            import subprocess
            out = subprocess.run(["sysctl", "-n", "hw.physicalcpu"], capture_output=True, text=True, timeout=5)
            return int(out.stdout.strip()) or logical
    except Exception:
        pass
    return logical


def _windows_cores() -> int:
    """Physical cores from GetLogicalProcessorInformation (one record with Relationship 0 per core)."""
    import ctypes
    from ctypes import wintypes

    class _Info(ctypes.Structure):
        _fields_ = [("mask", ctypes.c_size_t), ("relationship", ctypes.c_int), ("data", ctypes.c_ulonglong * 2)]

    size = wintypes.DWORD(0)
    get = ctypes.windll.kernel32.GetLogicalProcessorInformation
    get(None, ctypes.byref(size))
    count = size.value // ctypes.sizeof(_Info)
    if count == 0:
        return 0
    buf = (_Info * count)()
    if not get(buf, ctypes.byref(size)):
        return 0
    return sum(1 for info in buf if info.relationship == 0)


def default_threads() -> int:
    """Physical cores minus one (the GUI keeps a core), at least 1 and at most MAX_DEFAULT_THREADS."""
    return max(1, min(physical_cores() - 1, MAX_DEFAULT_THREADS))


def max_threads() -> int:
    """The largest sensible thread count (the number of logical processors)."""
    return os.cpu_count() or 1


def set_backend(name: str):
    name = (name or AUTO).lower()
    if name not in BACKENDS:
        raise ValueError(f"Unknown backend '{name}'; use one of {', '.join(BACKENDS)}.")
    _settings["backend"] = name


def backend() -> str:
    return _settings["backend"]


def set_threads(n):
    """Thread count of the Numba kernels; None or 0 = the default."""
    n = int(n) if n else None
    if n is not None:
        n = max(1, min(n, max_threads()))
    _settings["threads"] = n


def threads() -> int:
    """The thread count in effect."""
    return _settings["threads"] or default_threads()


# ---- memory (3D Euler stage) ------------------------------------------------------------------------------------

RUN_BYTES_PER_CELL = {2: 2500.0, 3: 4500.0}   # measured peak of a run incl. mesh (3D: 3.0 kB tetrahedra, 4.2 kB hexa)


def run_memory_estimate(n_cells, dim=3) -> float:
    """Memory a steady Euler run needs [bytes] (measured with tracemalloc on 64k-cell meshes, LU-SGS, see
    validation/timing.md; rounded up)."""
    return float(n_cells) * RUN_BYTES_PER_CELL.get(dim, RUN_BYTES_PER_CELL[3])


def free_memory_bytes():
    """Physical memory available now [bytes], or None if it cannot be found (no extra package needed)."""
    try:
        if os.name == "nt":
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return float(status.ullAvailPhys)
            return None
        return float(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None
