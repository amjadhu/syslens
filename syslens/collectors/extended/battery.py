import json
import platform
import re
import subprocess
from syslens.collectors.battery import collect as collect_basic


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


CHEMISTRY_MAP = {
    1: "Other", 2: "Unknown", 3: "Lead Acid", 4: "Nickel Cadmium",
    5: "Nickel Metal Hydride", 6: "Lithium Ion", 7: "Zinc Air",
    8: "Lithium Polymer",
}


# ── Windows ──────────────────────────────────────────────────────────────────

def _win_battery_extended():
    # Static data (design capacity, manufacturer)
    script_static = (
        "Get-WmiObject -Namespace 'root\\wmi' -Class BatteryStaticData | "
        "Select-Object DesignedCapacity,ManufactureName,DeviceName | "
        "ConvertTo-Json -Compress"
    )
    # Full charge capacity
    script_fcc = (
        "Get-WmiObject -Namespace 'root\\wmi' -Class BatteryFullChargedCapacity | "
        "Select-Object FullChargedCapacity | "
        "ConvertTo-Json -Compress"
    )
    # Real-time status
    script_status = (
        "Get-WmiObject -Namespace 'root\\wmi' -Class BatteryStatus | "
        "Select-Object RemainingCapacity,ChargeRate,DischargeRate,Charging,Discharging | "
        "ConvertTo-Json -Compress"
    )
    # Chemistry and basic info
    script_basic = (
        "Get-WmiObject Win32_Battery | "
        "Select-Object Chemistry,Manufacturer,Name,Status,EstimatedRunTime | "
        "ConvertTo-Json -Compress"
    )

    result = {}

    for script, key in [
        (script_static, "static"),
        (script_fcc, "fcc"),
        (script_status, "status"),
        (script_basic, "basic"),
    ]:
        raw = _run_ps(script)
        if raw:
            try:
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    data = data[0]
                result[key] = data
            except (json.JSONDecodeError, IndexError):
                pass

    static = result.get("static", {})
    fcc    = result.get("fcc", {})
    status = result.get("status", {})
    basic  = result.get("basic", {})

    design_cap    = static.get("DesignedCapacity")
    full_cap      = fcc.get("FullChargedCapacity")
    remaining_cap = status.get("RemainingCapacity")
    charge_rate   = status.get("ChargeRate")
    discharge_rate = status.get("DischargeRate")

    wear_pct = None
    if design_cap and full_cap and design_cap > 0:
        wear_pct = round((1 - full_cap / design_cap) * 100, 1)

    chem_int = basic.get("Chemistry")
    chemistry = CHEMISTRY_MAP.get(chem_int, "Unknown") if chem_int else "Unknown"

    return {
        "design_capacity_mwh":    design_cap,
        "full_charge_capacity_mwh": full_cap,
        "remaining_capacity_mwh": remaining_cap,
        "wear_pct":               wear_pct,
        "charge_rate_mw":         charge_rate,
        "discharge_rate_mw":      discharge_rate,
        "chemistry":              chemistry,
        "manufacturer":           (static.get("ManufactureName") or basic.get("Manufacturer") or "N/A").strip(),
        "device_name":            (static.get("DeviceName") or basic.get("Name") or "N/A").strip(),
    }


# ── macOS ─────────────────────────────────────────────────────────────────────

def _mac_battery_extended():
    out = _run(["ioreg", "-r", "-c", "AppleSmartBattery", "-d", "1"], timeout=6)
    fields = {}
    for line in out.splitlines():
        m = re.match(r'\s+"(\w+)"\s*=\s*(.+)', line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"')

    def _int(key):
        try:
            return int(fields.get(key, ""))
        except (ValueError, TypeError):
            return None

    design_cap = _int("DesignCapacity")
    max_cap    = _int("MaxCapacity")
    cur_cap    = _int("CurrentCapacity")
    amperage   = _int("Amperage")
    voltage    = _int("Voltage")
    cycles     = _int("CycleCount")
    temp       = _int("Temperature")

    wear_pct = None
    if design_cap and max_cap and design_cap > 0:
        wear_pct = round((1 - max_cap / design_cap) * 100, 1)

    power_mw = None
    if amperage is not None and voltage is not None:
        power_mw = round(abs(amperage) * voltage / 1_000_000 * 1000, 1)

    temp_c = round(temp / 100, 1) if temp else None

    return {
        "design_capacity_mah":    design_cap,
        "full_charge_capacity_mah": max_cap,
        "current_capacity_mah":   cur_cap,
        "cycle_count":            cycles,
        "wear_pct":               wear_pct,
        "power_mw":               power_mw,
        "charging":               fields.get("IsCharging") == "Yes",
        "temperature_c":          temp_c,
        "manufacturer":           fields.get("Manufacturer", "N/A"),
        "device_name":            fields.get("DeviceName", "N/A"),
    }


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    if system == "Windows":
        return {**basic, **_win_battery_extended()}

    elif system == "Darwin":
        return {**basic, **_mac_battery_extended()}

    return basic
