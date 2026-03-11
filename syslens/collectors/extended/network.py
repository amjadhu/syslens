import platform
import re
import subprocess
from syslens.collectors.network import collect as collect_basic


def _run(cmd, timeout=6):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8", errors="replace")
        return result.stdout.strip()
    except Exception:
        return ""


# ── Windows ──────────────────────────────────────────────────────────────────

def _win_ipconfig():
    out = _run(["ipconfig", "/all"], timeout=6)
    adapters = {}
    current = None

    for line in out.splitlines():
        # Adapter block header (not indented with spaces)
        if line and not line.startswith(" ") and "adapter" in line.lower():
            current = line.rstrip(":").strip()
            adapters[current] = {}
            continue
        if current is None:
            continue
        # ipconfig uses "Key . . . . : Value" — split on ` : ` after the dots
        if " : " in line:
            parts = line.split(" : ", 1)
            key = parts[0].strip().rstrip(". ")
            val = parts[1].strip()
            if key and val:
                adapters[current][key] = val

    # Extract per-adapter DNS, gateway, DHCP
    result = {}
    for name, fields in adapters.items():
        entry = {}
        for k, v in fields.items():
            kl = k.lower()
            if "dns server" in kl:
                entry.setdefault("dns_servers", []).append(v)
            elif "default gateway" in kl and v:
                entry["gateway"] = v
            elif "dhcp server" in kl:
                entry["dhcp_server"] = v
            elif "lease obtained" in kl:
                entry["lease_obtained"] = v
            elif "lease expires" in kl:
                entry["lease_expires"] = v
        if entry:
            result[name] = entry
    return result


def _win_wifi():
    out = _run(["netsh", "wlan", "show", "interfaces"], timeout=6)
    info = {}
    for line in out.splitlines():
        m = re.match(r"\s+(.+?)\s*:\s*(.+)", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        kl = key.lower()
        if "ssid" in kl and "bssid" not in kl:
            info["ssid"] = val
        elif "signal" in kl:
            pct = re.search(r"(\d+)%", val)
            if pct:
                pct_val = int(pct.group(1))
                info["signal_pct"] = pct_val
                info["signal_dbm"] = round((pct_val / 2) - 100, 0)
        elif "radio type" in kl:
            info["radio_type"] = val
        elif "channel" in kl:
            info["channel"] = val
        elif "authentication" in kl:
            info["security"] = val
        elif "receive rate" in kl:
            info["rx_mbps"] = val
        elif "transmit rate" in kl:
            info["tx_mbps"] = val
        elif "band" in kl:
            info["band"] = val

    # Infer band from channel if not provided
    if "channel" in info and "band" not in info:
        try:
            ch = int(info["channel"])
            if 1 <= ch <= 14:
                info["band"] = "2.4 GHz"
            elif 36 <= ch <= 177:
                info["band"] = "5 GHz"
            else:
                info["band"] = "6 GHz"
        except ValueError:
            pass

    return info if "ssid" in info else None


# ── macOS ─────────────────────────────────────────────────────────────────────

def _mac_dns_gateway():
    dns_servers = []
    out = _run(["scutil", "--dns"], timeout=5)
    for line in out.splitlines():
        m = re.match(r"\s+nameserver\[\d+\]\s*:\s*(.+)", line)
        if m:
            ip = m.group(1).strip()
            if ip not in dns_servers:
                dns_servers.append(ip)

    gateway = "N/A"
    out = _run(["netstat", "-rn", "-f", "inet"], timeout=5)
    for line in out.splitlines():
        if line.startswith("default"):
            parts = line.split()
            if len(parts) >= 2:
                gateway = parts[1]
                break

    return dns_servers, gateway


def _mac_wifi():
    airport = (
        "/System/Library/PrivateFrameworks/Apple80211.framework"
        "/Versions/Current/Resources/airport"
    )
    out = _run([airport, "-I"], timeout=5)
    info = {}
    for line in out.splitlines():
        m = re.match(r"\s+(.+?):\s*(.+)", line)
        if not m:
            continue
        key, val = m.group(1).strip(), m.group(2).strip()
        kl = key.lower()
        if kl == "ssid":
            info["ssid"] = val
        elif kl == "agrctlrssi":
            info["signal_dbm"] = int(val)
            info["signal_pct"] = max(0, min(100, 2 * (int(val) + 100)))
        elif kl == "channel":
            info["channel"] = val
        elif kl == "lasttxrate":
            info["tx_mbps"] = val
        elif kl == "maxrate":
            info["max_rate_mbps"] = val

    # Infer band from channel
    if "channel" in info and "band" not in info:
        try:
            ch = int(str(info["channel"]).split(",")[0])
            if 1 <= ch <= 14:
                info["band"] = "2.4 GHz"
            elif 36 <= ch <= 177:
                info["band"] = "5 GHz"
            else:
                info["band"] = "6 GHz"
        except ValueError:
            pass

    return info if "ssid" in info else None


# ── Public API ────────────────────────────────────────────────────────────────

def collect_extended():
    basic = collect_basic()
    system = platform.system()

    if system == "Windows":
        ip_config = _win_ipconfig()
        wifi      = _win_wifi()
        # Attach per-interface detail to basic interfaces
        for iface in basic.get("interfaces", []):
            name = iface["name"]
            for adapter_name, detail in ip_config.items():
                if name.lower() in adapter_name.lower() or adapter_name.lower() in name.lower():
                    iface.update(detail)
                    break
        return {**basic, "wifi": wifi}

    elif system == "Darwin":
        dns, gateway = _mac_dns_gateway()
        wifi = _mac_wifi()
        # Attach global DNS/gateway to basic
        basic["dns_servers"] = dns
        basic["gateway"]     = gateway
        return {**basic, "wifi": wifi}

    return basic
