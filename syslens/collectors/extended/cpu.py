import json
import platform
import subprocess
import psutil
from syslens.collectors.cpu import collect as collect_basic


def _run(cmd, timeout=8):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8", errors="replace")
        return result.stdout.strip()
    except Exception:
        return ""


def _run_ps(script, timeout=10):
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-OutputFormat", "Text", "-Command", script], timeout=timeout)


INTEL_MICROARCH = {
    (6, 85):  "Skylake-X / Cascade Lake",
    (6, 94):  "Skylake",
    (6, 142): "Kaby Lake / Whiskey Lake / Amber Lake",
    (6, 158): "Coffee Lake",
    (6, 165): "Comet Lake",
    (6, 167): "Rocket Lake",
    (6, 140): "Tiger Lake",
    (6, 141): "Alder Lake",
    (6, 183): "Raptor Lake",
    (6, 186): "Meteor Lake",
    (6, 143): "Sapphire Rapids",
    (6, 207): "Emerald Rapids",
}

CHEMISTRY_MAP = {20: "DDR", 21: "DDR2", 24: "DDR3", 26: "DDR4",
                 30: "LPDDR4", 34: "DDR5", 35: "LPDDR5"}


def _microarch():
    proc = platform.processor()
    # Try to extract Family/Model from brand string
    import re
    m = re.search(r"Family\s+(\d+)\s+Model\s+(\d+)", proc, re.IGNORECASE)
    if m:
        key = (int(m.group(1)), int(m.group(2)))
        return INTEL_MICROARCH.get(key, f"Family {key[0]} Model {key[1]}")
    # For ARM / Apple Silicon
    if "arm" in proc.lower() or platform.machine().lower() in ("arm64", "aarch64"):
        machine = platform.machine()
        return f"ARM ({machine})"
    return "N/A"


# ── Windows ──────────────────────────────────────────────────────────────────

def _win_cache_sizes():
    script = (
        "Get-WmiObject Win32_CacheMemory | "
        "Select-Object Level,InstalledSize | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        level_map = {3: "L1", 4: "L2", 5: "L3"}
        result = {}
        for entry in data:
            lvl = level_map.get(entry.get("Level"), f"L{entry.get('Level')}")
            size_kb = entry.get("InstalledSize") or 0
            result[lvl] = f"{size_kb} KB" if size_kb < 1024 else f"{size_kb // 1024} MB"
        return result
    except json.JSONDecodeError:
        return {}


def _win_virtualization():
    out = _run_ps("(Get-WmiObject Win32_Processor).VirtualizationFirmwareEnabled")
    return out.strip().lower() == "true"


def _win_power_plan():
    out = _run(["powercfg", "/getactivescheme"], timeout=5)
    import re
    m = re.search(r"\((.+?)\)\s*$", out)
    return m.group(1) if m else out.strip() or "N/A"


def _win_per_core_freq():
    freqs = psutil.cpu_freq(percpu=True)
    if freqs:
        return [round(f.current, 0) for f in freqs]
    return []


# ── macOS ─────────────────────────────────────────────────────────────────────

def _mac_cache_sizes():
    keys = ["hw.l1icachesize", "hw.l1dcachesize", "hw.l2cachesize", "hw.l3cachesize"]
    result = {}
    for key in keys:
        out = _run(["sysctl", "-n", key], timeout=3)
        if out.isdigit():
            size = int(out)
            label = key.split(".")[-1].replace("cachesize", "").upper()
            result[label] = f"{size // 1024} KB" if size < 1024 * 1024 else f"{size // (1024 * 1024)} MB"
    return result


def _mac_virtualization():
    out = _run(["sysctl", "-n", "machdep.cpu.features"], timeout=3)
    return "VMX" in out or platform.machine().lower() in ("arm64", "aarch64")


def _mac_power_mode():
    out = _run(["pmset", "-g"], timeout=3)
    for line in out.splitlines():
        if "powermode" in line.lower():
            parts = line.strip().split()
            mode_map = {"0": "Normal", "1": "Low Power", "2": "High Power"}
            return mode_map.get(parts[-1], parts[-1]) if parts else "N/A"
    return "N/A"


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    # Per-core frequencies (works cross-platform)
    per_core_freqs = []
    try:
        freqs = psutil.cpu_freq(percpu=True)
        if freqs:
            per_core_freqs = [round(f.current, 0) for f in freqs]
    except Exception:
        pass

    extended = {
        **basic,
        "microarchitecture": _microarch(),
        "per_core_freq_mhz": per_core_freqs,
    }

    if system == "Windows":
        extended["cache_sizes"]      = _win_cache_sizes()
        extended["virtualization"]   = _win_virtualization()
        extended["power_plan"]       = _win_power_plan()

    elif system == "Darwin":
        extended["cache_sizes"]      = _mac_cache_sizes()
        extended["virtualization"]   = _mac_virtualization()
        extended["power_plan"]       = _mac_power_mode()

    return extended
