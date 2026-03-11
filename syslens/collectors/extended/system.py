import json
import platform
import subprocess
from syslens.collectors.system import collect as collect_basic


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


CHASSIS_TYPES = {
    1: "Other", 2: "Unknown", 3: "Desktop", 4: "Low Profile Desktop",
    5: "Pizza Box", 6: "Mini Tower", 7: "Tower", 8: "Portable",
    9: "Laptop", 10: "Notebook", 11: "Hand Held", 12: "Docking Station",
    13: "All in One", 14: "Sub Notebook", 15: "Space-Saving",
    16: "Lunch Box", 17: "Main Server Chassis", 18: "Expansion Chassis",
    21: "Peripheral Chassis", 22: "RAID Chassis",
    23: "Rack Mount Chassis", 24: "Sealed-Case PC",
}


# ── Windows ──────────────────────────────────────────────────────────────────

def _win_bios():
    script = (
        "Get-WmiObject Win32_BIOS | "
        "Select-Object Manufacturer,SMBIOSBIOSVersion,ReleaseDate,Name | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        if isinstance(d, list):
            d = d[0]
        bios_date = "N/A"
        raw_date = d.get("ReleaseDate") or ""
        if raw_date and len(raw_date) >= 8:
            from datetime import datetime
            try:
                bios_date = datetime.strptime(raw_date[:8], "%Y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                pass
        return {
            "bios_vendor":  (d.get("Manufacturer") or "N/A").strip(),
            "bios_version": (d.get("SMBIOSBIOSVersion") or "N/A").strip(),
            "bios_date":    bios_date,
        }
    except (json.JSONDecodeError, IndexError):
        return {}


def _win_motherboard():
    script = (
        "Get-WmiObject Win32_BaseBoard | "
        "Select-Object Manufacturer,Product,Version | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        if isinstance(d, list):
            d = d[0]
        return {
            "board_vendor":  (d.get("Manufacturer") or "N/A").strip(),
            "board_model":   (d.get("Product") or "N/A").strip(),
            "board_version": (d.get("Version") or "N/A").strip(),
        }
    except (json.JSONDecodeError, IndexError):
        return {}


def _win_chassis():
    out = _run_ps("(Get-WmiObject Win32_SystemEnclosure).ChassisTypes")
    try:
        chassis_id = int(out.strip())
        return CHASSIS_TYPES.get(chassis_id, f"Type {chassis_id}")
    except (ValueError, TypeError):
        return "Unknown"


def _win_os_detail():
    script = (
        "Get-WmiObject Win32_OperatingSystem | "
        "Select-Object Caption,BuildNumber,OSArchitecture | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    release = _run_ps(
        r'(Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").DisplayVersion'
    )
    result = {"windows_release": release.strip() or "N/A"}
    if raw:
        try:
            d = json.loads(raw)
            if isinstance(d, list):
                d = d[0]
            result["os_edition"]    = (d.get("Caption") or "N/A").strip()
            result["build_number"]  = (d.get("BuildNumber") or "N/A").strip()
            result["os_arch"]       = (d.get("OSArchitecture") or "N/A").strip()
        except (json.JSONDecodeError, IndexError):
            pass
    return result


def _win_secure_boot():
    out = _run_ps("Confirm-SecureBootUEFI")
    v = out.strip().lower()
    if v == "true":
        return "Enabled"
    elif v == "false":
        return "Disabled"
    return "Legacy BIOS / N/A"


def _win_tpm():
    script = (
        "Get-Tpm | "
        "Select-Object TpmPresent,TpmReady,TpmEnabled,TpmVersion | "
        "ConvertTo-Json -Compress"
    )
    raw = _run_ps(script)
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        if isinstance(d, list):
            d = d[0]
        return {
            "tpm_present": d.get("TpmPresent"),
            "tpm_enabled": d.get("TpmEnabled"),
            "tpm_version": d.get("TpmVersion") or "N/A",
        }
    except (json.JSONDecodeError, IndexError):
        return {}


# ── macOS ─────────────────────────────────────────────────────────────────────

def _mac_hardware():
    raw = _run(["system_profiler", "SPHardwareDataType", "-json"], timeout=15)
    if not raw:
        return {}
    try:
        data = json.loads(raw).get("SPHardwareDataType", [{}])[0]
    except (json.JSONDecodeError, IndexError):
        return {}

    model = data.get("machine_model", "")
    chassis = "Laptop" if "macbook" in model.lower() else \
              "All-in-One" if "imac" in model.lower() else \
              "Desktop/Server"

    return {
        "board_model":    model,
        "board_vendor":   "Apple",
        "bios_version":   data.get("boot_rom_version", "N/A"),
        "chassis_type":   chassis,
        "serial_number":  data.get("serial_number", "N/A"),
        "cpu_type":       data.get("cpu_type", "N/A"),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    if system == "Windows":
        extended = {
            **basic,
            **_win_bios(),
            **_win_motherboard(),
            **_win_os_detail(),
            "chassis_type":  _win_chassis(),
            "secure_boot":   _win_secure_boot(),
            **_win_tpm(),
        }
        return extended

    elif system == "Darwin":
        return {**basic, **_mac_hardware()}

    return basic
