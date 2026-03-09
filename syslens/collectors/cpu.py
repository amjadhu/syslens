import psutil


def collect():
    # Two-pass for accurate per-core usage
    psutil.cpu_percent(interval=None, percpu=True)
    usage = psutil.cpu_percent(interval=0.5)
    per_core = psutil.cpu_percent(interval=None, percpu=True)

    freq = psutil.cpu_freq()

    data = {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "usage_percent": usage,
        "per_core_usage": per_core,
    }

    if freq:
        data["frequency_mhz"] = {
            "current": round(freq.current, 1),
            "min": round(freq.min, 1),
            "max": round(freq.max, 1),
        }

    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for key in ["coretemp", "cpu_thermal", "k10temp", "acpitz"]:
                if key in temps:
                    data["temperature_celsius"] = round(temps[key][0].current, 1)
                    break
    except AttributeError:
        pass  # Not supported on Windows

    return data
