import platform
import subprocess


def _run(cmd, timeout=5):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


def _collect_windows():
    gpus = []
    out = _run(["wmic", "path", "win32_VideoController", "get",
                "Name,AdapterRAM,DriverVersion,VideoProcessor", "/format:csv"])
    lines = [l for l in out.split("\n") if l.strip()]
    # Skip header lines (Node,AdapterRAM,...)
    for line in lines:
        parts = line.split(",")
        if len(parts) < 4 or "AdapterRAM" in line:
            continue
        try:
            vram_bytes = int(parts[1]) if parts[1].strip().isdigit() else 0
            vram_gb = round(vram_bytes / (1024 ** 3), 2) if vram_bytes > 0 else "N/A"
        except (ValueError, IndexError):
            vram_gb = "N/A"
        name = parts[3].strip() if len(parts) > 3 else "Unknown"
        driver = parts[2].strip() if len(parts) > 2 else "N/A"
        if name:
            gpus.append({"name": name, "vram_gb": vram_gb, "driver": driver})
    return gpus


def _collect_macos():
    gpus = []
    out = _run(["system_profiler", "SPDisplaysDataType"], timeout=10)
    current = {}
    for line in out.split("\n"):
        line = line.strip()
        if "Chipset Model:" in line:
            if current:
                gpus.append(current)
            current = {"name": line.split(":", 1)[1].strip()}
        elif "VRAM" in line and ":" in line:
            current["vram"] = line.split(":", 1)[1].strip()
        elif "Metal:" in line:
            current["metal"] = line.split(":", 1)[1].strip()
        elif "Vendor:" in line:
            current["vendor"] = line.split(":", 1)[1].strip()
    if current:
        gpus.append(current)
    return gpus


def collect():
    system = platform.system()
    if system == "Windows":
        gpus = _collect_windows()
    elif system == "Darwin":
        gpus = _collect_macos()
    else:
        gpus = []
    return {"gpus": gpus}
