import json
import platform
import re
import subprocess
from datetime import datetime

import psutil


# Windows event IDs related to shutdown / restart / boot
# 6005  EventLog   — service started  → system just booted
# 6006  EventLog   — service stopped  → clean shutdown
# 6008  EventLog   — unexpected prior shutdown (power / freeze)
# 41    Kernel-Power — unexpected restart (power loss or crash)
# 1074  User32      — initiated shutdown/restart with reason code
_PS_QUERY = (
    "Get-WinEvent -FilterHashtable @{"
    "LogName='System';"
    "Id=41,1074,6005,6006,6008"
    "} -MaxEvents 40 -ErrorAction SilentlyContinue | "
    "Select-Object "
    "@{N='Time';E={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}},"
    "Id,ProviderName,"
    "@{N='Message';E={$_.Message.Substring(0,[Math]::Min(600,$_.Message.Length))}} | "
    "ConvertTo-Json -Depth 2 -Compress"
)

# Reason codes that appear in Event 1074 messages
_REASON_CODES = {
    0x80040001: "Windows Update",
    0x40040001: "Application maintenance (planned)",
    0x00040001: "Application maintenance",
    0x80050012: "Service pack installation",
    0x40030011: "Other (user-initiated, planned)",
    0x00030011: "Other (user-initiated)",
    0x40020004: "Hardware maintenance (planned)",
    0x00020004: "Hardware maintenance",
    0x80020004: "Hardware failure",
}


def _extract_1074_detail(message):
    """Return (shutdown_type, reason_str) from a 1074 message."""
    msg_lower = message.lower()

    # Shutdown type: "restart" or "power-off" / "shutdown"
    shutdown_type = "restart" if "restart" in msg_lower else "shutdown"

    # Try "Comment:" line first
    for line in message.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("comment:"):
            comment = stripped[8:].strip()
            if comment:
                return shutdown_type, comment

    # Try to match known reason codes
    code_match = re.search(r'reason\s+code[:\s]+0x([0-9a-fA-F]+)', message, re.IGNORECASE)
    if code_match:
        code = int(code_match.group(1), 16)
        if code in _REASON_CODES:
            return shutdown_type, _REASON_CODES[code]

    # Heuristic: check executable name in message
    if "wuauclt" in msg_lower or "tiworker" in msg_lower or "windows update" in msg_lower:
        return shutdown_type, "Windows Update"
    if "winlogon" in msg_lower:
        return shutdown_type, "User initiated"

    return shutdown_type, ""


def _classify(event_id, message):
    """Return (kind, label, color) for a single event."""
    msg_lower = message.lower()

    if event_id == 6005:
        return "boot", "System started (boot)", "green"

    if event_id == 6006:
        return "clean_shutdown", "System shut down cleanly", "blue"

    if event_id == 6008:
        # Extract a clean HH:MM:SS AM/PM and M/D/YYYY date from the message.
        # Windows embeds invisible Unicode direction markers around date components
        # that get corrupted during console capture, so we extract only digit/colon
        # patterns rather than relying on the raw text.
        time_part = re.search(r'(\d{1,2}:\d{2}:\d{2}\s*[AP]M)', message, re.IGNORECASE)
        # Windows embeds invisible Unicode direction markers before date digits;
        # they arrive as '?' via the console code page, so match around them.
        date_part = re.search(r'\?*(\d{1,2})\?*/\?*(\d{1,2})\?*/\?*(\d{4})', message)
        if time_part and date_part:
            m, d, y = date_part.group(1), date_part.group(2), date_part.group(3)
            when = f" (last seen {time_part.group(1)} on {m}/{d}/{y})"
        elif time_part:
            when = f" (last seen {time_part.group(1)})"
        else:
            when = ""
        return "power_loss", f"Unexpected shutdown{when} — power loss, freeze, or hard reset", "red"

    if event_id == 41:
        code_match = re.search(r'bugcheckcode\s+(\d+)', msg_lower)
        if code_match:
            code = int(code_match.group(1))
            if code == 0:
                return "power_loss", "Power cut or hard reset — no BSOD code (BugcheckCode 0)", "red"
            return "crash", f"System crash (BSOD) — stop code 0x{code:08X}", "red"
        return "unexpected", "Unexpected restart (power or hardware issue)", "red"

    if event_id == 1074:
        shutdown_type, reason = _extract_1074_detail(message)
        if shutdown_type == "restart":
            label = f"Clean restart — {reason}" if reason else "Clean restart"
            return "restart", label, "cyan"
        label = f"Clean shutdown — {reason}" if reason else "Clean shutdown"
        return "shutdown", label, "blue"

    return "unknown", "Unknown event", "dim"


def _collect_windows():
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-OutputFormat", "Text", "-Command", _PS_QUERY],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
        raw = result.stdout.strip()
        if not raw:
            return [], "No reboot-related events found in the System log"
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed = [parsed]
        return parsed, None
    except json.JSONDecodeError as e:
        return [], f"Failed to parse event log JSON: {e}"
    except subprocess.TimeoutExpired:
        return [], "Event log query timed out"
    except FileNotFoundError:
        return [], "powershell.exe not found"
    except Exception as e:
        return [], str(e)


def _collect_macos():
    events = []
    error = None
    try:
        result = subprocess.run(
            ["last", "-F", "reboot"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if not line.strip() or "reboot" not in line.lower():
                continue
            # Format: reboot   ~   <day> <month> <date> <time> <year>
            parts = line.split()
            if len(parts) >= 7:
                try:
                    # Reconstruct: "Mon Mar 25 10:30:00 2026"
                    time_str = " ".join(parts[2:7])
                    dt = datetime.strptime(time_str, "%a %b %d %H:%M:%S %Y")
                    events.append({
                        "Time": dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "Id": 6005,
                        "ProviderName": "last(1)",
                        "Message": "System reboot",
                    })
                except ValueError:
                    pass
    except Exception as e:
        error = str(e)

    # pmset log for power/sleep events (last 50 lines)
    try:
        result = subprocess.run(
            ["pmset", "-g", "log"],
            capture_output=True, text=True, timeout=10,
        )
        lines = result.stdout.splitlines()
        for line in lines[-50:]:
            ll = line.lower()
            if any(k in ll for k in ("sleep", "wake", "hibernat", "shutdown", "restart")):
                events.append({
                    "Time": line[:19],
                    "Id": 0,
                    "ProviderName": "pmset",
                    "Message": line.strip(),
                })
    except Exception:
        pass

    return events, error


def collect():
    system = platform.system()

    boot_ts = psutil.boot_time()
    boot_dt = datetime.fromtimestamp(boot_ts)
    boot_time_str = boot_dt.strftime("%Y-%m-%d %H:%M:%S")

    delta = datetime.now() - boot_dt
    total = int(delta.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        uptime_str = f"{days}d {hours}h {mins}m"
    elif hours:
        uptime_str = f"{hours}h {mins}m"
    else:
        uptime_str = f"{mins}m"

    if system == "Windows":
        raw_events, error = _collect_windows()
    elif system == "Darwin":
        raw_events, error = _collect_macos()
    else:
        raw_events, error = [], f"Reboot history not supported on {system}"

    # Build timeline (events arrive newest-first from PowerShell)
    timeline = []
    for e in raw_events:
        event_id = int(e.get("Id") or 0)
        message  = (e.get("Message") or "").replace("\r\n", "\n").strip()
        time_str = (e.get("Time") or "")
        provider = (e.get("ProviderName") or "")

        kind, label, color = _classify(event_id, message)
        timeline.append({
            "time":     time_str,
            "event_id": event_id,
            "kind":     kind,
            "label":    label,
            "color":    color,
            "provider": provider,
        })

    # Determine last restart reason:
    # Find the first "boot" event (= current boot), then look at the next
    # entry (which is older) for what triggered it.
    last_reason       = "Unknown — no matching events found"
    last_kind         = "unknown"
    last_color        = "dim"
    found_current_boot = False

    for ev in timeline:
        if ev["kind"] == "boot" and not found_current_boot:
            found_current_boot = True
            continue
        if found_current_boot:
            last_reason = ev["label"]
            last_kind   = ev["kind"]
            last_color  = ev["color"]
            break

    # Fallback: if no boot event found in window, use most recent
    # non-boot event as a best guess
    if not found_current_boot and timeline:
        for ev in timeline:
            if ev["kind"] not in ("boot",):
                last_reason = ev["label"]
                last_kind   = ev["kind"]
                last_color  = ev["color"]
                break

    return {
        "platform":      system,
        "last_boot":     boot_time_str,
        "uptime":        uptime_str,
        "last_reason":   last_reason,
        "last_kind":     last_kind,
        "last_color":    last_color,
        "timeline":      timeline,
        "error":         error,
    }
