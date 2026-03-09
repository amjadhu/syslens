import psutil


def collect():
    # First pass to initialize CPU percent tracking
    procs = []
    for p in psutil.process_iter(["pid", "name", "status"]):
        try:
            p.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Short sleep for accurate readings happens implicitly via the interval in main collect
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username"]):
        try:
            info = p.info
            info["cpu_percent"] = info.get("cpu_percent") or 0.0
            info["memory_percent"] = round(info.get("memory_percent") or 0.0, 2)
            procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    top_cpu = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:10]
    top_mem = sorted(procs, key=lambda x: x["memory_percent"], reverse=True)[:10]

    return {
        "total": len(procs),
        "top_cpu": top_cpu,
        "top_memory": top_mem,
    }
