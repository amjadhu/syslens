import json
import platform
import subprocess
from syslens.collectors.disk import collect as collect_basic


def _run(cmd, timeout=8):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8", errors="replace")
        return result.stdout.strip()
    except Exception:
        return ""


def _run_ps(script, timeout=12):
    return _run(["powershell.exe", "-NoProfile", "-NonInteractive",
                 "-OutputFormat", "Text", "-Command", script], timeout=timeout)


def _to_gb(b):
    return round(b / (1024 ** 3), 2) if b else 0


# ── Windows ──────────────────────────────────────────────────────────────────

def _win_physical_drives():
    script = (
        "Get-WmiObject Win32_DiskDrive | "
        "Select-Object Model,SerialNumber,FirmwareRevision,"
        "InterfaceType,MediaType,Size,PNPDeviceID | "
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

    drives = []
    for d in data:
        pnp = (d.get("PNPDeviceID") or "").upper()
        iface = (d.get("InterfaceType") or "Unknown").strip()
        media = (d.get("MediaType") or "").strip()
        model = (d.get("Model") or "Unknown").strip()

        # Refine interface type
        if "NVME" in pnp or "NVME" in model.upper():
            iface = "NVMe"
        elif "USB" in pnp:
            iface = "USB"
        elif iface == "IDE":
            iface = "SATA/IDE"

        # Media type — also infer SSD from NVMe interface or model name
        if "ssd" in media.lower() or "solid" in media.lower():
            drive_type = "SSD"
        elif iface == "NVMe" or "nvme" in model.lower() or "ssd" in model.lower():
            drive_type = "SSD"
        elif "fixed hard disk" in media.lower() or "hdd" in model.lower():
            drive_type = "HDD"
        else:
            drive_type = "Unknown"

        size = d.get("Size") or 0
        drives.append({
            "model":        model,
            "serial":       (d.get("SerialNumber") or "N/A").strip(),
            "firmware":     (d.get("FirmwareRevision") or "N/A").strip(),
            "interface":    iface,
            "drive_type":   drive_type,
            "size_gb":      _to_gb(int(size)) if str(size).isdigit() else 0,
        })
    return drives


def _win_smart_health():
    script = (
        "Get-PhysicalDisk | "
        "Select-Object FriendlyName,MediaType,HealthStatus,OperationalStatus,Size | "
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

    return [
        {
            "name":   (d.get("FriendlyName") or "Unknown").strip(),
            "type":   (d.get("MediaType") or "Unknown").strip(),
            "health": (d.get("HealthStatus") or "Unknown").strip(),
            "status": (d.get("OperationalStatus") or "Unknown").strip(),
            "size_gb": _to_gb(int(d.get("Size") or 0)),
        }
        for d in data
    ]


# ── macOS ─────────────────────────────────────────────────────────────────────

def _mac_physical_drives():
    raw = _run(["system_profiler", "SPStorageDataType", "-json"], timeout=15)
    if not raw:
        return [], []
    try:
        data = json.loads(raw).get("SPStorageDataType", [])
    except (json.JSONDecodeError, AttributeError):
        return [], []

    drives, health = [], []
    seen = set()
    for vol in data:
        phys = vol.get("physical_drive", {})
        model = phys.get("device_name", "Unknown")
        if model not in seen:
            seen.add(model)
            drives.append({
                "model":      model,
                "serial":     phys.get("serial_number", "N/A"),
                "firmware":   phys.get("revision", "N/A"),
                "interface":  phys.get("protocol", "N/A"),
                "drive_type": phys.get("medium_type", "Unknown"),
            })
            smart = phys.get("smart_status", "N/A")
            health.append({
                "name":   model,
                "type":   phys.get("medium_type", "N/A"),
                "health": "Healthy" if smart == "Verified" else smart,
                "status": smart,
            })
    return drives, health


# ── Top Folders by Size ───────────────────────────────────────────────────────

def _top_folders(mountpoint, top_n=5):
    """Return top N immediate subdirectories by size under a mountpoint."""
    system = platform.system()
    try:
        if system == "Windows":
            script = (
                f"Get-ChildItem -Directory -Force '{mountpoint}' -ErrorAction SilentlyContinue | "
                f"ForEach-Object {{ $size = (Get-ChildItem $_.FullName -Recurse -Force -File "
                f"-ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum "
                f"-ErrorAction SilentlyContinue).Sum; "
                f"[PSCustomObject]@{{Path=$_.FullName;Size=[math]::Round($size/1GB,2)}} }} | "
                f"Sort-Object Size -Descending | Select-Object -First {top_n} | "
                f"ConvertTo-Json -Compress"
            )
            raw = _run_ps(script, timeout=30)
            if not raw:
                return []
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            return [{"path": d["Path"], "size_gb": d["Size"]} for d in data if d.get("Size")]
        else:
            # macOS / Linux: du -d 1 (depth 1)
            raw = _run(["du", "-d", "1", "-k", mountpoint], timeout=30)
            if not raw:
                return []
            entries = []
            for line in raw.splitlines():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    continue
                size_kb, path = parts
                path = path.strip()
                if path == mountpoint or path == mountpoint.rstrip("/"):
                    continue
                try:
                    size_gb = round(int(size_kb) / (1024 * 1024), 2)
                    entries.append({"path": path, "size_gb": size_gb})
                except ValueError:
                    continue
            entries.sort(key=lambda e: e["size_gb"], reverse=True)
            return entries[:top_n]
    except Exception:
        return []


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    # Collect top folders for major partitions only (>10 GB, real filesystems)
    top_folders = {}
    skip_fs = {"nullfs", "devfs", "tmpfs", "devtmpfs", "squashfs", "overlay"}
    for p in basic.get("partitions", []):
        if p.get("total_gb", 0) < 10:
            continue
        if p.get("fstype", "").lower() in skip_fs:
            continue
        mp = p["mountpoint"]
        # Skip macOS internal system volumes, but keep /System/Volumes/Data
        if mp.startswith("/System/Volumes/") and mp != "/System/Volumes/Data":
            continue
        folders = _top_folders(mp)
        if folders:
            top_folders[mp] = folders

    if system == "Windows":
        return {
            **basic,
            "physical_drives": _win_physical_drives(),
            "smart_health":    _win_smart_health(),
            "top_folders":     top_folders,
        }

    elif system == "Darwin":
        drives, health = _mac_physical_drives()
        return {
            **basic,
            "physical_drives": drives,
            "smart_health":    health,
            "top_folders":     top_folders,
        }

    return {**basic, "top_folders": top_folders}
