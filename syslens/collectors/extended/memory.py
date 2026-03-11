import json
import platform
import subprocess
from syslens.collectors.memory import collect as collect_basic


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


SMBIOS_TYPE = {
    20: "DDR", 21: "DDR2", 22: "DDR2 FB-DIMM", 24: "DDR3",
    26: "DDR4", 27: "LPDDR", 28: "LPDDR2", 29: "LPDDR3",
    30: "LPDDR4", 34: "DDR5", 35: "LPDDR5",
}

FORM_FACTOR = {
    1: "Other", 2: "Unknown", 3: "SIMM", 4: "SIP", 5: "Chip",
    6: "DIP", 7: "ZIP", 8: "Proprietary Card", 9: "DIMM",
    10: "TSOP", 11: "Row of chips", 12: "RIMM", 13: "SODIMM",
    14: "SRIMM", 15: "FB-DIMM", 16: "Die",
}


# ── Windows ──────────────────────────────────────────────────────────────────

def _win_dimm_slots():
    script = (
        "Get-WmiObject Win32_PhysicalMemoryArray | "
        "Select-Object MemoryDevices,MaxCapacity | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    total_slots, max_cap_kb = None, None
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            if data:
                total_slots = data[0].get("MemoryDevices")
                max_cap_kb  = data[0].get("MaxCapacity")
        except json.JSONDecodeError:
            pass
    return total_slots, max_cap_kb


def _win_dimms():
    script = (
        "Get-WmiObject Win32_PhysicalMemory | "
        "Select-Object BankLabel,DeviceLocator,Manufacturer,PartNumber,"
        "SerialNumber,Capacity,Speed,SMBIOSMemoryType,FormFactor | "
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

    dimms = []
    for d in data:
        cap = d.get("Capacity") or 0
        cap_gb = round(cap / (1024 ** 3), 1) if cap else 0
        mem_type = SMBIOS_TYPE.get(d.get("SMBIOSMemoryType"), "Unknown")
        form = FORM_FACTOR.get(d.get("FormFactor"), "Unknown")
        dimms.append({
            "slot":         f"{d.get('BankLabel', '')} {d.get('DeviceLocator', '')}".strip(),
            "manufacturer": (d.get("Manufacturer") or "N/A").strip(),
            "part_number":  (d.get("PartNumber") or "N/A").strip(),
            "serial":       (d.get("SerialNumber") or "N/A").strip(),
            "capacity_gb":  cap_gb,
            "speed_mhz":    d.get("Speed") or "N/A",
            "type":         mem_type,
            "form_factor":  form,
            "populated":    cap_gb > 0,
        })
    return dimms


# ── macOS ─────────────────────────────────────────────────────────────────────

def _mac_dimms():
    raw = _run(["system_profiler", "SPMemoryDataType", "-json"], timeout=15)
    if not raw:
        return []
    try:
        data = json.loads(raw).get("SPMemoryDataType", [])
    except (json.JSONDecodeError, AttributeError):
        return []

    dimms = []
    for entry in data:
        # Top-level entry may have _items (per-slot) or be the slot itself
        items = entry.get("_items") or [entry]
        for item in items:
            dimms.append({
                "slot":         item.get("_name", "N/A"),
                "manufacturer": item.get("dimm_manufacturer", "N/A"),
                "part_number":  item.get("dimm_part_number", "N/A"),
                "capacity_gb":  item.get("dimm_size", "N/A"),
                "speed_mhz":    item.get("dimm_speed", "N/A"),
                "type":         item.get("dimm_type", "N/A"),
                "form_factor":  "N/A",
                "populated":    item.get("dimm_size", "") not in ("", "Empty"),
            })
    return dimms


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    if system == "Windows":
        dimms = _win_dimms()
        total_slots, max_cap_kb = _win_dimm_slots()
        populated = sum(1 for d in dimms if d["populated"])
        max_cap_gb = round(max_cap_kb / (1024 * 1024), 0) if max_cap_kb else None
        return {
            **basic,
            "dimms":          dimms,
            "total_slots":    total_slots,
            "populated_slots": populated,
            "max_capacity_gb": max_cap_gb,
        }

    elif system == "Darwin":
        dimms = _mac_dimms()
        return {
            **basic,
            "dimms":          dimms,
            "total_slots":    len(dimms),
            "populated_slots": sum(1 for d in dimms if d["populated"]),
            "max_capacity_gb": None,
        }

    return basic
