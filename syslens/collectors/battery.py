import psutil


def collect():
    battery = psutil.sensors_battery()
    if battery is None:
        return {"available": False}

    time_left = None
    if battery.secsleft > 0 and not battery.power_plugged:
        time_left = round(battery.secsleft / 60, 1)

    return {
        "available": True,
        "percent": round(battery.percent, 1),
        "plugged_in": battery.power_plugged,
        "time_left_minutes": time_left,
    }
