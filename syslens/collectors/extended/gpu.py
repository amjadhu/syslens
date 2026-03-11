import json
import platform
import subprocess
from syslens.collectors.gpu import collect as collect_basic


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


# ── Windows ──────────────────────────────────────────────────────────────────

def _nvidia_smi():
    out = _run([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,utilization.memory,"
        "memory.used,memory.total,temperature.gpu,"
        "clocks.current.graphics,clocks.current.memory,driver_version",
        "--format=csv,noheader,nounits"
    ], timeout=5)
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 9:
            continue
        try:
            gpus.append({
                "name":            parts[0],
                "gpu_usage_pct":   int(parts[1]),
                "mem_usage_pct":   int(parts[2]),
                "vram_used_mb":    int(parts[3]),
                "vram_total_mb":   int(parts[4]),
                "temperature_c":   int(parts[5]),
                "core_clock_mhz":  int(parts[6]),
                "mem_clock_mhz":   int(parts[7]),
                "driver_version":  parts[8],
                "source":          "nvidia-smi",
            })
        except (ValueError, IndexError):
            continue
    return gpus


def _wmi_gpu_extended():
    script = (
        "Get-WmiObject Win32_VideoController | "
        "Select-Object Name,AdapterRAM,DriverVersion,DriverDate,"
        "CurrentHorizontalResolution,CurrentVerticalResolution,"
        "CurrentRefreshRate,VideoProcessor,AdapterCompatibility | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError:
        return []

    gpus = []
    for g in data:
        name = (g.get("Name") or "").strip()
        if not name:
            continue
        vram_bytes = g.get("AdapterRAM") or 0
        vram_gb = round(vram_bytes / (1024 ** 3), 2) if vram_bytes else "N/A"

        driver_date = "N/A"
        raw_date = g.get("DriverDate") or ""
        if raw_date and len(raw_date) >= 8:
            try:
                from datetime import datetime
                driver_date = datetime.strptime(raw_date[:8], "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                pass

        res_h = g.get("CurrentHorizontalResolution")
        res_v = g.get("CurrentVerticalResolution")
        resolution = f"{res_h}×{res_v}" if res_h and res_v else "N/A"
        refresh = g.get("CurrentRefreshRate") or "N/A"

        gpus.append({
            "name":            name,
            "vram_gb":         vram_gb,
            "driver_version":  (g.get("DriverVersion") or "N/A").strip(),
            "driver_date":     driver_date,
            "video_processor": (g.get("VideoProcessor") or "N/A").strip(),
            "vendor":          (g.get("AdapterCompatibility") or "N/A").strip(),
            "resolution":      resolution,
            "refresh_hz":      refresh,
            "source":          "wmi",
        })
    return gpus


def _wmi_displays():
    script = (
        "Get-WmiObject Win32_DesktopMonitor | "
        "Select-Object Name,ScreenWidth,ScreenHeight | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
        return [
            {
                "name":   (d.get("Name") or "Monitor").strip(),
                "width":  d.get("ScreenWidth"),
                "height": d.get("ScreenHeight"),
            }
            for d in data if d.get("ScreenWidth")
        ]
    except json.JSONDecodeError:
        return []


def _directx_version():
    script = (
        r'(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\DirectX").Version'
    )
    return _run_ps(script) or "N/A"


# ── macOS ─────────────────────────────────────────────────────────────────────

def _macos_gpu_extended():
    raw = _run(["system_profiler", "SPDisplaysDataType", "-json"], timeout=15)
    if not raw:
        return [], []
    try:
        data = json.loads(raw).get("SPDisplaysDataType", [])
    except (json.JSONDecodeError, AttributeError):
        return [], []

    gpus, displays = [], []
    for entry in data:
        gpu = {
            "name":    entry.get("sppci_model", "Unknown"),
            "vendor":  entry.get("sppci_vendor", "N/A"),
            "vram":    entry.get("sppci_vram", "N/A"),
            "metal":   entry.get("spdisplays_mtlgpufamilysupport", "N/A"),
            "source":  "system_profiler",
        }
        gpus.append(gpu)
        for disp in entry.get("spdisplays_ndrvs", []):
            res  = disp.get("_spdisplays_resolution", "")
            rate = disp.get("spdisplays_refresh_rate", "")
            displays.append({
                "name":         disp.get("_name", "Display"),
                "resolution":   res,
                "refresh_rate": rate,
            })
    return gpus, displays


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    if system == "Windows":
        nvidia = _nvidia_smi()
        wmi    = _wmi_gpu_extended()
        # Merge nvidia-smi detail onto matching WMI entries (by name prefix)
        merged = []
        for w in wmi:
            match = next((n for n in nvidia if n["name"].lower() in w["name"].lower()
                          or w["name"].lower() in n["name"].lower()), None)
            if match:
                merged.append({**w, **match, "name": w["name"]})
            else:
                merged.append(w)
        # Add any NVIDIA cards not in WMI list (edge case)
        wmi_names = {g["name"].lower() for g in wmi}
        for n in nvidia:
            if not any(n["name"].lower() in w for w in wmi_names):
                merged.append(n)

        return {
            "gpus":         merged or basic["gpus"],
            "displays":     _wmi_displays(),
            "directx":      _directx_version(),
        }

    elif system == "Darwin":
        gpus, displays = _macos_gpu_extended()
        return {
            "gpus":     gpus or basic["gpus"],
            "displays": displays,
        }

    return basic
