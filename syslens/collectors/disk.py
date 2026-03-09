import psutil


def _to_gb(b):
    return round(b / (1024 ** 3), 2)


def collect():
    partitions = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            partitions.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total_gb": _to_gb(usage.total),
                "used_gb": _to_gb(usage.used),
                "free_gb": _to_gb(usage.free),
                "percent": usage.percent,
            })
        except (PermissionError, OSError):
            continue

    io = psutil.disk_io_counters()
    io_stats = None
    if io:
        io_stats = {
            "read_gb": _to_gb(io.read_bytes),
            "write_gb": _to_gb(io.write_bytes),
            "read_count": io.read_count,
            "write_count": io.write_count,
        }

    return {
        "partitions": partitions,
        "io_stats": io_stats,
    }
