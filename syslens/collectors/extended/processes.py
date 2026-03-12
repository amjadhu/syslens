import subprocess
from datetime import datetime

import psutil
from syslens.collectors.processes import collect as collect_basic


def _get_process_detail(p):
    try:
        info = p.as_dict(attrs=[
            "pid", "name", "status", "username",
            "cpu_percent", "memory_percent", "memory_info",
            "num_threads", "create_time", "ppid",
        ])
        # Command line — can fail on protected processes
        try:
            info["cmdline"] = " ".join(p.cmdline())[:120] or info["name"]
        except (psutil.AccessDenied, psutil.ZombieProcess):
            info["cmdline"] = info["name"]
        # Start time
        try:
            info["started"] = datetime.fromtimestamp(info["create_time"]).strftime("%H:%M:%S")
        except (OSError, TypeError):
            info["started"] = "N/A"
        # Memory in MB
        mem = info.get("memory_info")
        info["rss_mb"] = round(mem.rss / (1024 ** 2), 1) if mem else 0
        info["vms_mb"] = round(mem.vms / (1024 ** 2), 1) if mem else 0
        info["cpu_percent"] = info.get("cpu_percent") or 0.0
        info["memory_percent"] = round(info.get("memory_percent") or 0.0, 2)
        return info
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def collect_extended():
    # Prime CPU percent
    for p in psutil.process_iter(["pid"]):
        try:
            p.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    import time
    time.sleep(0.3)

    all_procs = []
    status_counts = {}

    for p in psutil.process_iter():
        detail = _get_process_detail(p)
        if detail:
            all_procs.append(detail)
            status = detail.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1

    # Skip System Idle Process (PID 0) and System (PID 4) from top lists
    rankable = [p for p in all_procs if p["pid"] not in (0, 4)]

    top_cpu = sorted(rankable, key=lambda x: x["cpu_percent"], reverse=True)[:15]
    top_mem = sorted(rankable, key=lambda x: x["memory_percent"], reverse=True)[:15]

    return {
        "total":         len(all_procs),
        "status_counts": status_counts,
        "top_cpu":       top_cpu,
        "top_memory":    top_mem,
    }
