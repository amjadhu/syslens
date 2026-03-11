import json
import os
import platform
import subprocess
import time
from datetime import datetime, timedelta

import psutil


# ---------------------------------------------------------------------------
# Event categorization
# ---------------------------------------------------------------------------

CATEGORIES = [
    ("driver_issues", ["driver", "dxgkrnl", "nvlddmkm", "igfx", "storport",
                       "usbhub", "hidclass", "ndis", "tcpip", "netbt"]),
    ("disk_errors",   ["disk", "ntfs", "fat32", "bad block", "i/o error",
                       "harddisk", "chkdsk", "volmgr", "storport", "cdrom"]),
    ("service_failures", ["service control manager", "servicecontrolmanager",
                          "service", "failed to start", "terminated unexpectedly"]),
    ("app_crashes",   ["application error", "faulting application", ".exe",
                       "crash", "exception", "hang", "windows error reporting"]),
]

DISK_EVENT_IDS    = {7, 11, 15, 55, 153, 157, 129}
APP_CRASH_IDS     = {1000, 1001, 1002, 1026}
SERVICE_FAIL_IDS  = {7022, 7023, 7024, 7031, 7034, 7038}


def _categorize(provider: str, message: str, event_id: int) -> str:
    provider_l = provider.lower()
    message_l  = message[:300].lower()

    if event_id in DISK_EVENT_IDS:
        return "disk_errors"
    if event_id in APP_CRASH_IDS:
        return "app_crashes"
    if event_id in SERVICE_FAIL_IDS:
        return "service_failures"

    for category, keywords in CATEGORIES:
        for kw in keywords:
            if kw in provider_l or kw in message_l:
                return category

    return "other"


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------

_PS_QUERY = (
    "Get-WinEvent -FilterHashtable @{"
    "LogName='System','Application';"
    "Level=1,2;"
    "StartTime=(Get-Date).AddHours(-24)"
    "} -ErrorAction SilentlyContinue | "
    "Select-Object "
    "@{N='Time';E={$_.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')}},"
    "Id,LevelDisplayName,ProviderName,"
    "@{N='Message';E={$_.Message.Substring(0,[Math]::Min(300,$_.Message.Length))}} | "
    "ConvertTo-Json -Depth 2 -Compress"
)


def _query_windows_events():
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-OutputFormat", "Text", "-Command", _PS_QUERY],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
        raw = result.stdout.strip()
        if not raw:
            return [], None
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


def _collect_windows():
    raw_events, error = _query_windows_events()

    buckets = {
        "driver_issues":    [],
        "disk_errors":      [],
        "service_failures": [],
        "app_crashes":      [],
        "other":            [],
    }

    for e in raw_events:
        provider   = (e.get("ProviderName") or "").strip()
        message    = (e.get("Message") or "").replace("\r\n", " ").replace("\n", " ").strip()
        event_id   = e.get("Id") or 0
        level      = (e.get("LevelDisplayName") or "Error").strip()
        time_str   = (e.get("Time") or "")

        category = _categorize(provider, message, event_id)
        severity = "critical" if level == "Critical" else "warning"

        finding = {
            "time":     time_str,
            "id":       event_id,
            "level":    level,
            "provider": provider,
            "message":  message[:120],
            "severity": severity,
            "source":   "event_log",
        }
        buckets[category].append(finding)

    return buckets, len(raw_events), error


# ---------------------------------------------------------------------------
# macOS
# ---------------------------------------------------------------------------

def _collect_macos():
    buckets = {
        "driver_issues":    [],
        "disk_errors":      [],
        "service_failures": [],
        "app_crashes":      [],
        "other":            [],
    }
    error = None

    try:
        result = subprocess.run(
            ["log", "show", "--last", "24h", "--style", "json",
             "--predicate", "messageType == fault OR messageType == error"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        raw = result.stdout.strip()
        if raw:
            events = json.loads(raw)
            if isinstance(events, dict):
                events = [events]
            for e in events[:200]:
                provider = e.get("subsystem") or e.get("category") or ""
                message  = (e.get("eventMessage") or "").replace("\n", " ")[:300]
                level    = e.get("messageType", "error")
                time_str = e.get("timestamp", "")[:19]

                category = _categorize(provider, message, 0)
                severity = "critical" if level == "fault" else "warning"

                buckets[category].append({
                    "time":     time_str,
                    "id":       None,
                    "level":    level,
                    "provider": provider,
                    "message":  message[:120],
                    "severity": severity,
                    "source":   "system_log",
                })
    except subprocess.TimeoutExpired:
        error = "System log query timed out (>30s)"
    except json.JSONDecodeError:
        error = "Failed to parse system log JSON"
    except Exception as e:
        error = str(e)

    # Crash reports
    crash_dirs = [
        os.path.expanduser("~/Library/Logs/DiagnosticReports"),
        "/Library/Logs/DiagnosticReports",
    ]
    cutoff = time.time() - 86400
    for crash_dir in crash_dirs:
        if not os.path.isdir(crash_dir):
            continue
        try:
            for entry in os.scandir(crash_dir):
                if entry.stat().st_mtime < cutoff:
                    continue
                if not entry.name.endswith((".crash", ".ips")):
                    continue
                try:
                    with open(entry.path, "r", errors="replace") as f:
                        first_lines = "".join(f.readline() for _ in range(8))
                    buckets["app_crashes"].append({
                        "time":     datetime.fromtimestamp(entry.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                        "id":       None,
                        "level":    "Error",
                        "provider": "DiagnosticReports",
                        "message":  first_lines.replace("\n", " ")[:120],
                        "severity": "warning",
                        "source":   "crash_report",
                    })
                except OSError:
                    continue
        except PermissionError:
            continue

    total = sum(len(v) for v in buckets.values())
    return buckets, total, error


# ---------------------------------------------------------------------------
# Heuristic checks (live system data)
# ---------------------------------------------------------------------------

def _heuristic_checks():
    findings = []

    # Disk space
    for part in psutil.disk_partitions():
        try:
            u = psutil.disk_usage(part.mountpoint)
            if u.percent > 85:
                sev = "critical" if u.percent > 95 else "warning"
                findings.append({
                    "category": "disk_errors",
                    "severity": sev,
                    "message": (
                        f"Disk {part.mountpoint} is {u.percent:.1f}% full "
                        f"({round(u.free / (1024**3), 1)} GB free of "
                        f"{round(u.total / (1024**3), 1)} GB)"
                    ),
                    "source": "heuristic",
                    "heuristic_key": "disk_full_critical" if u.percent > 95 else "disk_full_warning",
                })
        except (PermissionError, OSError):
            continue

    # RAM pressure
    vm = psutil.virtual_memory()
    if vm.percent > 90:
        findings.append({
            "category": "other",
            "severity": "critical",
            "message": (
                f"RAM usage is critically high at {vm.percent:.1f}% "
                f"({round(vm.available / (1024**3), 2)} GB available)"
            ),
            "source": "heuristic",
            "heuristic_key": "ram_critical",
        })
    elif vm.percent > 80:
        findings.append({
            "category": "other",
            "severity": "warning",
            "message": f"RAM usage is elevated at {vm.percent:.1f}%",
            "source": "heuristic",
            "heuristic_key": "ram_warning",
        })

    # Network errors
    io = psutil.net_io_counters()
    if io.errin + io.errout > 100:
        findings.append({
            "category": "other",
            "severity": "warning",
            "message": (
                f"Network has accumulated {io.errin} inbound and "
                f"{io.errout} outbound errors since last boot"
            ),
            "source": "heuristic",
            "heuristic_key": "network_errors",
        })

    # CPU hogs — two-pass for accuracy
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    time.sleep(0.3)
    cpu_count = psutil.cpu_count(logical=True) or 1
    for p in psutil.process_iter(["pid", "name", "cpu_percent"]):
        try:
            pct = p.info["cpu_percent"] or 0.0
            # Normalize by CPU count and skip OS idle/kernel pseudo-processes
            normalized = pct / cpu_count
            if p.info["pid"] in (0, 4):
                continue
            if normalized > 50:
                findings.append({
                    "category": "other",
                    "severity": "warning",
                    "message": (
                        f"Process '{p.info['name']}' (PID {p.info['pid']}) "
                        f"is consuming {pct:.1f}% CPU"
                    ),
                    "source": "heuristic",
                    "heuristic_key": "cpu_hog",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect():
    system = platform.system()

    if system == "Windows":
        events, event_count, error = _collect_windows()
    elif system == "Darwin":
        events, event_count, error = _collect_macos()
    else:
        events = {k: [] for k in ["driver_issues", "disk_errors",
                                   "service_failures", "app_crashes", "other"]}
        event_count = 0
        error = f"Event log collection not supported on {system}"

    heuristics = _heuristic_checks()

    critical_count = sum(
        1 for bucket in events.values()
        for f in bucket if f["severity"] == "critical"
    ) + sum(1 for f in heuristics if f["severity"] == "critical")

    warning_count = sum(
        1 for bucket in events.values()
        for f in bucket if f["severity"] == "warning"
    ) + sum(1 for f in heuristics if f["severity"] == "warning")

    return {
        "platform":       system,
        "generated_at":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lookback_hours": 24,
        "events":         events,
        "heuristics":     heuristics,
        "event_count":    event_count,
        "critical_count": critical_count,
        "warning_count":  warning_count,
        "error":          error,
    }
