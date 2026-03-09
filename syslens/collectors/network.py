import socket
import urllib.request
import psutil


def _to_mb(b):
    return round(b / (1024 ** 2), 2)


def _get_public_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=3) as r:
            return r.read().decode()
    except Exception:
        return "N/A"


def collect():
    interfaces = []
    stats = psutil.net_if_stats()

    for name, addrs in psutil.net_if_addrs().items():
        iface = {"name": name, "addresses": [], "is_up": False, "speed_mbps": None}

        if name in stats:
            iface["is_up"] = stats[name].isup
            if stats[name].speed > 0:
                iface["speed_mbps"] = stats[name].speed

        for addr in addrs:
            if addr.family == socket.AF_INET:
                iface["addresses"].append({
                    "type": "IPv4",
                    "address": addr.address,
                    "netmask": addr.netmask,
                })
            elif addr.family == socket.AF_INET6:
                iface["addresses"].append({
                    "type": "IPv6",
                    "address": addr.address,
                })

        if iface["addresses"]:
            interfaces.append(iface)

    io = psutil.net_io_counters()

    return {
        "public_ip": _get_public_ip(),
        "interfaces": interfaces,
        "io_stats": {
            "bytes_sent_mb": _to_mb(io.bytes_sent),
            "bytes_recv_mb": _to_mb(io.bytes_recv),
            "packets_sent": io.packets_sent,
            "packets_recv": io.packets_recv,
            "errors_in": io.errin,
            "errors_out": io.errout,
        },
    }
