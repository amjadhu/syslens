"""Extended section renderers — used when --section is specified."""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.columns import Columns
from rich.text import Text

console = Console()


def _kv_table(rows: list[tuple], color: str = "cyan") -> Table:
    """Two-column key/value table."""
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Key", style="dim", no_wrap=True, min_width=22)
    t.add_column("Value", style=color)
    for k, v in rows:
        if v not in (None, "", "N/A", "Unknown", []):
            t.add_row(str(k), str(v))
        else:
            t.add_row(str(k), "[dim]N/A[/dim]")
    return t


def _health_color(status: str) -> str:
    s = (status or "").lower()
    if s in ("healthy", "ok", "verified", "enabled"):
        return "green"
    if s in ("warning", "degraded"):
        return "yellow"
    if s in ("unhealthy", "failing", "failed", "error"):
        return "red"
    return "white"


# ── GPU ───────────────────────────────────────────────────────────────────────

def render_gpu(data):
    console.print()
    console.rule("[bold red]  GPU — Extended Detail  [/bold red]")
    console.print()

    for i, g in enumerate(data.get("gpus", []), 1):
        rows = [
            ("Name",             g.get("name")),
            ("Vendor",           g.get("vendor") or g.get("AdapterCompatibility")),
            ("Video Processor",  g.get("video_processor")),
            ("VRAM",             f"{g.get('vram_gb')} GB" if g.get('vram_gb') not in (None, 'N/A') else g.get('vram')),
            ("VRAM Used / Total", f"{g.get('vram_used_mb')} / {g.get('vram_total_mb')} MB"
                                  if g.get('vram_total_mb') else None),
            ("GPU Usage",        f"{g.get('gpu_usage_pct')}%" if g.get('gpu_usage_pct') is not None else None),
            ("Memory Usage",     f"{g.get('mem_usage_pct')}%" if g.get('mem_usage_pct') is not None else None),
            ("Temperature",      f"{g.get('temperature_c')}°C" if g.get('temperature_c') is not None else None),
            ("Core Clock",       f"{g.get('core_clock_mhz')} MHz" if g.get('core_clock_mhz') else None),
            ("Memory Clock",     f"{g.get('mem_clock_mhz')} MHz" if g.get('mem_clock_mhz') else None),
            ("Driver Version",   g.get("driver_version") or g.get("driver")),
            ("Driver Date",      g.get("driver_date")),
            ("Metal Support",    g.get("metal")),
            ("Resolution",       g.get("resolution")),
            ("Refresh Rate",     f"{g.get('refresh_hz')} Hz" if g.get('refresh_hz') not in (None, 'N/A') else None),
            ("Data Source",      g.get("source")),
        ]
        rows = [(k, v) for k, v in rows if v not in (None, "", "N/A", "Unknown")]
        console.print(Panel(_kv_table(rows, "cyan"),
                            title=f"[bold red]GPU {i}: {g.get('name', 'Unknown')}[/bold red]",
                            border_style="red"))
        console.print()

    # DirectX
    dx = data.get("directx")
    if dx and dx != "N/A":
        console.print(Panel(f"[cyan]{dx}[/cyan]",
                            title="[bold]DirectX Version[/bold]", border_style="dim"))
        console.print()

    # Connected displays
    displays = data.get("displays", [])
    if displays:
        t = Table(box=box.SIMPLE, header_style="bold magenta", padding=(0, 1))
        t.add_column("Display")
        t.add_column("Resolution")
        t.add_column("Refresh Rate")
        for d in displays:
            res   = d.get("resolution") or (f"{d.get('width')}×{d.get('height')}" if d.get("width") else "N/A")
            rate  = d.get("refresh_rate") or (f"{d.get('refresh_hz')} Hz" if d.get("refresh_hz") else "N/A")
            t.add_row(d.get("name", "Display"), str(res), str(rate))
        console.print(Panel(t, title="[bold magenta]Connected Displays[/bold magenta]",
                            border_style="magenta"))
        console.print()


# ── CPU ───────────────────────────────────────────────────────────────────────

def render_cpu(data):
    console.print()
    console.rule("[bold green]  CPU — Extended Detail  [/bold green]")
    console.print()

    rows = [
        ("Processor",          data.get("processor") or data.get("microarchitecture")),
        ("Microarchitecture",  data.get("microarchitecture")),
        ("Physical Cores",     data.get("physical_cores")),
        ("Logical Cores",      data.get("logical_cores")),
        ("Overall Usage",      f"{data.get('usage_percent')}%"),
        ("Base Frequency",     f"{data.get('frequency_mhz', {}).get('current')} MHz"
                               if data.get("frequency_mhz") else None),
        ("Max Frequency",      f"{data.get('frequency_mhz', {}).get('max')} MHz"
                               if data.get("frequency_mhz") else None),
        ("Temperature",        f"{data.get('temperature_celsius')}°C"
                               if data.get("temperature_celsius") else None),
        ("Virtualization",     "Supported" if data.get("virtualization") else
                               ("Not Supported" if data.get("virtualization") is False else None)),
        ("Power Plan",         data.get("power_plan")),
    ]
    rows = [(k, v) for k, v in rows if v not in (None, "", "N/A")]

    cache = data.get("cache_sizes", {})
    for lvl in ("L1I", "L1D", "L1", "L2", "L3"):
        if lvl in cache:
            rows.append((f"Cache {lvl}", cache[lvl]))

    console.print(Panel(_kv_table(rows, "green"),
                        title="[bold green]CPU Overview[/bold green]",
                        border_style="green"))
    console.print()

    # Per-core usage
    per_core = data.get("per_core_usage", [])
    if per_core:
        per_core_freqs = data.get("per_core_freq_mhz", [])
        t = Table(box=box.SIMPLE, header_style="bold green", padding=(0, 1))
        t.add_column("Core", justify="right", width=6)
        t.add_column("Usage %", justify="right", width=9)
        t.add_column("Freq MHz", justify="right", width=10)
        t.add_column("Bar", min_width=20)

        for i, usage in enumerate(per_core):
            color = "green" if usage < 50 else "yellow" if usage < 80 else "red"
            bar_len = int(usage / 5)
            bar = f"[{color}]{'#' * bar_len}{'-' * (20 - bar_len)}[/{color}]"
            freq = str(int(per_core_freqs[i])) if i < len(per_core_freqs) else "N/A"
            t.add_row(str(i), f"[{color}]{usage:.1f}[/{color}]", freq, bar)

        console.print(Panel(t, title="[bold green]Per-Core Detail[/bold green]",
                            border_style="green"))
        console.print()


# ── Memory ────────────────────────────────────────────────────────────────────

def render_memory(data):
    console.print()
    console.rule("[bold yellow]  Memory — Extended Detail  [/bold yellow]")
    console.print()

    ram  = data.get("ram", {})
    swap = data.get("swap", {})
    overview_rows = [
        ("RAM Total",           f"{ram.get('total_gb')} GB"),
        ("RAM Used",            f"{ram.get('used_gb')} GB ({ram.get('percent')}%)"),
        ("RAM Available",       f"{ram.get('available_gb')} GB"),
        ("Swap Total",          f"{swap.get('total_gb')} GB"),
        ("Swap Used",           f"{swap.get('used_gb')} GB ({swap.get('percent')}%)"),
        ("Physical Slots",      f"{data.get('populated_slots')} used / {data.get('total_slots')} total"
                                if data.get("total_slots") else None),
        ("Max Supported",       f"{int(data.get('max_capacity_gb', 0))} GB"
                                if data.get("max_capacity_gb") else None),
    ]
    console.print(Panel(_kv_table([(k, v) for k, v in overview_rows if v], "yellow"),
                        title="[bold yellow]Memory Overview[/bold yellow]",
                        border_style="yellow"))
    console.print()

    # DIMM table
    dimms = data.get("dimms", [])
    if dimms:
        t = Table(box=box.SIMPLE, header_style="bold yellow", padding=(0, 1))
        t.add_column("Slot")
        t.add_column("Status", width=10)
        t.add_column("Size", justify="right")
        t.add_column("Type")
        t.add_column("Speed")
        t.add_column("Form Factor")
        t.add_column("Manufacturer")
        t.add_column("Part Number")

        for d in dimms:
            status     = "[green]Populated[/green]" if d["populated"] else "[dim]Empty[/dim]"
            cap        = f"{d['capacity_gb']} GB" if d["populated"] and d.get("capacity_gb") else "—"
            speed      = str(d.get("speed_mhz", "N/A"))
            if speed != "N/A" and not speed.endswith("Hz"):
                speed += " MHz"
            t.add_row(
                d.get("slot", ""),
                status,
                cap,
                str(d.get("type", "N/A")),
                speed,
                str(d.get("form_factor", "N/A")),
                str(d.get("manufacturer", "N/A")),
                str(d.get("part_number", "N/A")),
            )
        console.print(Panel(t, title="[bold yellow]DIMM Slots[/bold yellow]",
                            border_style="yellow"))
        console.print()


# ── Disk ──────────────────────────────────────────────────────────────────────

def render_disk(data):
    console.print()
    console.rule("[bold magenta]  Disk — Extended Detail  [/bold magenta]")
    console.print()

    # SMART health
    smart = data.get("smart_health", [])
    if smart:
        t = Table(box=box.SIMPLE, header_style="bold magenta", padding=(0, 1))
        t.add_column("Drive")
        t.add_column("Type")
        t.add_column("Size", justify="right")
        t.add_column("Health")
        t.add_column("Status")

        for d in smart:
            hc  = _health_color(d.get("health", ""))
            sc  = _health_color(d.get("status", ""))
            size = f"{d.get('size_gb', 0):.0f} GB" if d.get("size_gb") else "N/A"
            t.add_row(
                d.get("name", "Unknown"),
                d.get("type", "N/A"),
                size,
                f"[{hc}]{d.get('health', 'N/A')}[/{hc}]",
                f"[{sc}]{d.get('status', 'N/A')}[/{sc}]",
            )
        console.print(Panel(t, title="[bold magenta]SMART Health[/bold magenta]",
                            border_style="magenta"))
        console.print()

    # Physical drives
    drives = data.get("physical_drives", [])
    if drives:
        t = Table(box=box.SIMPLE, header_style="bold magenta", padding=(0, 1))
        t.add_column("Model")
        t.add_column("Interface")
        t.add_column("Type")
        t.add_column("Size", justify="right")
        t.add_column("Serial")
        t.add_column("Firmware")

        for d in drives:
            size = f"{d.get('size_gb', 0):.0f} GB" if d.get("size_gb") else "N/A"
            t.add_row(
                d.get("model", "Unknown"),
                d.get("interface", "N/A"),
                d.get("drive_type", "N/A"),
                size,
                d.get("serial", "N/A"),
                d.get("firmware", "N/A"),
            )
        console.print(Panel(t, title="[bold magenta]Physical Drives[/bold magenta]",
                            border_style="magenta"))
        console.print()

    # Partition table (from basic)
    partitions = data.get("partitions", [])
    if partitions:
        t = Table(box=box.SIMPLE, header_style="bold magenta", padding=(0, 1))
        t.add_column("Device", style="dim")
        t.add_column("Mount")
        t.add_column("FS")
        t.add_column("Total", justify="right")
        t.add_column("Used", justify="right")
        t.add_column("Free", justify="right")
        t.add_column("Usage", justify="right")
        for p in partitions:
            color = "green" if p["percent"] < 70 else "yellow" if p["percent"] < 90 else "red"
            t.add_row(p["device"], p["mountpoint"], p["fstype"],
                      f"{p['total_gb']} GB", f"{p['used_gb']} GB", f"{p['free_gb']} GB",
                      f"[{color}]{p['percent']}%[/{color}]")
        console.print(Panel(t, title="[bold magenta]Partitions[/bold magenta]",
                            border_style="magenta"))
        console.print()


# ── Network ───────────────────────────────────────────────────────────────────

def render_network(data):
    console.print()
    console.rule("[bold cyan]  Network — Extended Detail  [/bold cyan]")
    console.print()

    # WiFi detail
    wifi = data.get("wifi")
    if wifi:
        rows = [
            ("SSID",          wifi.get("ssid")),
            ("Band",          wifi.get("band")),
            ("Channel",       wifi.get("channel")),
            ("Signal",        f"{wifi.get('signal_pct')}% ({wifi.get('signal_dbm')} dBm)"
                              if wifi.get("signal_pct") is not None else None),
            ("Radio Type",    wifi.get("radio_type")),
            ("Security",      wifi.get("security")),
            ("RX Rate",       f"{wifi.get('rx_mbps')} Mbps" if wifi.get("rx_mbps") else None),
            ("TX Rate",       f"{wifi.get('tx_mbps')} Mbps" if wifi.get("tx_mbps") else None),
            ("Max Rate",      f"{wifi.get('max_rate_mbps')} Mbps" if wifi.get("max_rate_mbps") else None),
        ]
        rows = [(k, v) for k, v in rows if v]
        console.print(Panel(_kv_table(rows, "cyan"),
                            title="[bold cyan]Wi-Fi[/bold cyan]", border_style="cyan"))
        console.print()

    # Global DNS / gateway
    dns = data.get("dns_servers", [])
    gateway = data.get("gateway")
    if dns or gateway:
        lines = []
        if gateway:
            lines.append(f"Default Gateway: [cyan]{gateway}[/cyan]")
        if dns:
            lines.append("DNS Servers: " + "  ".join(f"[cyan]{d}[/cyan]" for d in dns))
        console.print(Panel("\n".join(lines), title="[bold cyan]Routing[/bold cyan]",
                            border_style="cyan"))
        console.print()

    # Interfaces
    for iface in data.get("interfaces", []):
        status = "[green]up[/green]" if iface.get("is_up") else "[red]down[/red]"
        speed  = f" • {iface['speed_mbps']} Mbps" if iface.get("speed_mbps") else ""
        rows = [
            ("Status",        f"{status}{speed}"),
            ("IPv4",          next((a["address"] for a in iface.get("addresses", [])
                                    if a["type"] == "IPv4"), None)),
            ("Netmask",       next((a.get("netmask") for a in iface.get("addresses", [])
                                    if a["type"] == "IPv4" and a.get("netmask")), None)),
            ("IPv6",          next((a["address"] for a in iface.get("addresses", [])
                                    if a["type"] == "IPv6"), None)),
            ("Gateway",       iface.get("gateway")),
            ("DNS Servers",   ", ".join(iface["dns_servers"]) if iface.get("dns_servers") else None),
            ("DHCP Server",   iface.get("dhcp_server")),
            ("Lease Obtained", iface.get("lease_obtained")),
            ("Lease Expires",  iface.get("lease_expires")),
        ]
        rows = [(k, v) for k, v in rows if v]
        if rows:
            console.print(Panel(_kv_table(rows, "cyan"),
                                title=f"[bold cyan]{iface['name']}[/bold cyan]",
                                border_style="dim"))
            console.print()

    # I/O stats
    io = data.get("io_stats", {})
    if io:
        io_rows = [
            ("Bytes Sent",    f"{io.get('bytes_sent_mb')} MB"),
            ("Bytes Received", f"{io.get('bytes_recv_mb')} MB"),
            ("Packets Sent",  io.get("packets_sent")),
            ("Packets Received", io.get("packets_recv")),
            ("Errors In / Out", f"{io.get('errors_in')} / {io.get('errors_out')}"),
        ]
        console.print(Panel(_kv_table(io_rows, "cyan"),
                            title="[bold cyan]I/O Statistics[/bold cyan]",
                            border_style="cyan"))
        console.print()


# ── Battery ───────────────────────────────────────────────────────────────────

def render_battery(data):
    console.print()
    console.rule("[bold]  Battery — Extended Detail  [/bold]")
    console.print()

    if not data.get("available"):
        console.print(Panel("[dim]No battery detected.[/dim]", border_style="white"))
        return

    pct   = data.get("percent", 0)
    color = "green" if pct > 50 else "yellow" if pct > 20 else "red"

    wear = data.get("wear_pct")
    wear_color = "green" if wear is not None and wear < 10 else \
                 "yellow" if wear is not None and wear < 25 else "red"
    wear_str = f"[{wear_color}]{wear}%[/{wear_color}] battery wear" if wear is not None else None

    rows = [
        ("Charge",                f"[{color}]{pct}%[/{color}]"),
        ("Status",                "Plugged in" if data.get("plugged_in") else "On battery"),
        ("Time Remaining",        f"{data.get('time_left_minutes')} min"
                                  if data.get("time_left_minutes") else None),
        ("Design Capacity",       f"{data.get('design_capacity_mwh')} mWh"
                                  if data.get("design_capacity_mwh") else
                                  (f"{data.get('design_capacity_mah')} mAh"
                                   if data.get("design_capacity_mah") else None)),
        ("Full Charge Capacity",  f"{data.get('full_charge_capacity_mwh')} mWh"
                                  if data.get("full_charge_capacity_mwh") else
                                  (f"{data.get('full_charge_capacity_mah')} mAh"
                                   if data.get("full_charge_capacity_mah") else None)),
        ("Battery Wear",          wear_str),
        ("Charge Cycles",         data.get("cycle_count")),
        ("Power Draw",            f"{data.get('power_mw')} mW" if data.get("power_mw") else None),
        ("Charge Rate",           f"{data.get('charge_rate_mw')} mW" if data.get("charge_rate_mw") else None),
        ("Discharge Rate",        f"{data.get('discharge_rate_mw')} mW" if data.get("discharge_rate_mw") else None),
        ("Temperature",           f"{data.get('temperature_c')}°C" if data.get("temperature_c") else None),
        ("Chemistry",             data.get("chemistry")),
        ("Manufacturer",          data.get("manufacturer")),
        ("Device Name",           data.get("device_name")),
    ]
    rows = [(k, v) for k, v in rows if v not in (None, "", "N/A", "Unknown")]
    console.print(Panel(_kv_table(rows), title="[bold]Battery[/bold]", border_style="white"))
    console.print()


# ── System ────────────────────────────────────────────────────────────────────

def render_system(data):
    console.print()
    console.rule("[bold blue]  System — Extended Detail  [/bold blue]")
    console.print()

    overview_rows = [
        ("Hostname",          data.get("hostname")),
        ("OS",                f"{data.get('os')} {data.get('os_release')} ({data.get('architecture')})"),
        ("Edition",           data.get("os_edition")),
        ("Windows Release",   data.get("windows_release")),
        ("Build Number",      data.get("build_number")),
        ("OS Architecture",   data.get("os_arch")),
        ("Uptime",            data.get("uptime")),
        ("Boot Time",         data.get("boot_time")),
        ("Python Version",    data.get("python_version")),
    ]
    console.print(Panel(_kv_table([(k, v) for k, v in overview_rows if v], "blue"),
                        title="[bold blue]Operating System[/bold blue]",
                        border_style="blue"))
    console.print()

    hardware_rows = [
        ("Chassis Type",      data.get("chassis_type")),
        ("Board Vendor",      data.get("board_vendor")),
        ("Board Model",       data.get("board_model")),
        ("Board Version",     data.get("board_version")),
        ("CPU Type",          data.get("cpu_type")),
        ("Serial Number",     data.get("serial_number")),
        ("BIOS Vendor",       data.get("bios_vendor")),
        ("BIOS Version",      data.get("bios_version")),
        ("BIOS Date",         data.get("bios_date")),
    ]
    console.print(Panel(_kv_table([(k, v) for k, v in hardware_rows if v], "blue"),
                        title="[bold blue]Hardware / Firmware[/bold blue]",
                        border_style="blue"))
    console.print()

    security_rows = [
        ("Secure Boot",       data.get("secure_boot")),
        ("TPM Present",       "Yes" if data.get("tpm_present") else
                              ("No" if data.get("tpm_present") is False else None)),
        ("TPM Enabled",       "Yes" if data.get("tpm_enabled") else
                              ("No" if data.get("tpm_enabled") is False else None)),
        ("TPM Version",       data.get("tpm_version")),
    ]
    security_rows = [(k, v) for k, v in security_rows if v]
    if security_rows:
        console.print(Panel(_kv_table(security_rows, "blue"),
                            title="[bold blue]Security[/bold blue]",
                            border_style="blue"))
        console.print()


# ── Processes ────────────────────────────────────────────────────────────────

def render_processes(data):
    console.print()
    console.rule("[bold green]  Processes — Extended Detail  [/bold green]")
    console.print()

    total = data.get("total", 0)
    status_counts = data.get("status_counts", {})

    # Summary
    status_str = "  ".join(
        f"[dim]{k}[/dim]: [cyan]{v}[/cyan]"
        for k, v in sorted(status_counts.items(), key=lambda x: -x[1])
    )
    console.print(Panel(
        f"Total: [bold cyan]{total}[/bold cyan]  |  {status_str}",
        title="[bold green]Process Summary[/bold green]",
        border_style="green",
    ))
    console.print()

    def _proc_table(procs, title, sort_col):
        t = Table(box=box.SIMPLE, header_style="bold green", padding=(0, 1))
        t.add_column("PID",     justify="right", width=7, style="dim")
        t.add_column("Name",    width=22, no_wrap=True)
        t.add_column("CPU%",    justify="right", width=7)
        t.add_column("MEM%",    justify="right", width=7)
        t.add_column("RSS MB",  justify="right", width=8)
        t.add_column("Threads", justify="right", width=8)
        t.add_column("User",    width=14, style="dim", no_wrap=True)
        t.add_column("Started", width=9, style="dim")
        t.add_column("Command", no_wrap=True)

        for p in procs:
            cpu_pct = p.get("cpu_percent", 0)
            mem_pct = p.get("memory_percent", 0)
            cpu_c = "green" if cpu_pct < 10 else "yellow" if cpu_pct < 50 else "red"
            mem_c = "green" if mem_pct < 5  else "yellow" if mem_pct < 15  else "red"
            t.add_row(
                str(p.get("pid", "")),
                p.get("name", ""),
                f"[{cpu_c}]{cpu_pct:.1f}[/{cpu_c}]",
                f"[{mem_c}]{mem_pct:.2f}[/{mem_c}]",
                str(p.get("rss_mb", "")),
                str(p.get("num_threads", "")),
                (p.get("username") or "")[:14],
                p.get("started", ""),
                p.get("cmdline", ""),
            )
        return Panel(t, title=f"[bold green]{title}[/bold green]", border_style="green")

    console.print(_proc_table(data.get("top_cpu", []),    "Top 15 by CPU",    "cpu"))
    console.print()
    console.print(_proc_table(data.get("top_memory", []), "Top 15 by Memory", "mem"))
    console.print()


# ── Software ──────────────────────────────────────────────────────────────────

def render_software(data):
    console.print()
    console.rule("[bold blue]  Software — Extended Detail  [/bold blue]")
    console.print()

    # Installed runtimes with paths
    installed = data.get("installed", {})
    if installed:
        t = Table(box=box.SIMPLE, header_style="bold blue", padding=(0, 1))
        t.add_column("Runtime", style="cyan bold", width=12)
        t.add_column("Version")
        t.add_column("Path", style="dim")
        for name, info in installed.items():
            if isinstance(info, dict):
                t.add_row(name, info.get("version", "N/A"), info.get("path", "N/A"))
            else:
                t.add_row(name, str(info), "N/A")
        console.print(Panel(t, title="[bold blue]Installed Runtimes[/bold blue]",
                            border_style="blue"))
        console.print()

    # pip packages
    pip_pkgs = data.get("pip_packages", [])
    pip_outdated = data.get("pip_outdated", [])
    outdated_names = {p["name"].lower() for p in pip_outdated}

    if pip_pkgs:
        t = Table(box=box.SIMPLE, header_style="bold cyan", padding=(0, 1),
                  title=f"Python Packages ({len(pip_pkgs)} installed, "
                        f"[yellow]{len(pip_outdated)} outdated[/yellow])")
        t.add_column("Package", width=28)
        t.add_column("Version",  width=16)
        t.add_column("Status",   width=10)
        for pkg in sorted(pip_pkgs, key=lambda x: x["name"].lower()):
            is_out = pkg["name"].lower() in outdated_names
            outdated_entry = next((p for p in pip_outdated
                                   if p["name"].lower() == pkg["name"].lower()), None)
            status = f"[yellow]-> {outdated_entry['latest_version']}[/yellow]" \
                     if outdated_entry else "[dim]up to date[/dim]"
            t.add_row(pkg["name"], pkg["version"], status)
        console.print(Panel(t, title="[bold cyan]pip Packages[/bold cyan]",
                            border_style="cyan"))
        console.print()

    # npm global packages
    npm_pkgs = data.get("npm_global", {})
    if npm_pkgs:
        t = Table(box=box.SIMPLE, header_style="bold yellow", padding=(0, 1))
        t.add_column("Package", style="cyan", width=30)
        t.add_column("Version")
        for name, version in sorted(npm_pkgs.items()):
            t.add_row(name, version)
        console.print(Panel(t, title=f"[bold yellow]npm Global Packages ({len(npm_pkgs)})[/bold yellow]",
                            border_style="yellow"))
        console.print()

    # Environment variables
    env_vars = data.get("env_vars", {})
    if env_vars:
        t = Table(box=box.SIMPLE, header_style="bold magenta", padding=(0, 1))
        t.add_column("Variable",  style="cyan", width=22)
        t.add_column("Value",     style="dim")
        for k, v in sorted(env_vars.items()):
            t.add_row(k, v[:80])
        console.print(Panel(t, title="[bold magenta]Dev Environment Variables[/bold magenta]",
                            border_style="magenta"))
        console.print()

    # PATH entries
    path_entries = data.get("path_entries", [])
    if path_entries:
        t = Table(box=box.SIMPLE, header_style="bold dim", padding=(0, 1))
        t.add_column("#",    justify="right", width=4, style="dim")
        t.add_column("Path", style="dim")
        for i, entry in enumerate(path_entries, 1):
            t.add_row(str(i), entry)
        console.print(Panel(t, title="[bold]PATH Entries[/bold]", border_style="dim"))
        console.print()


# ── Router ────────────────────────────────────────────────────────────────────

SECTION_EXTENDED_RENDERERS = {
    "gpu":       render_gpu,
    "cpu":       render_cpu,
    "memory":    render_memory,
    "disk":      render_disk,
    "network":   render_network,
    "battery":   render_battery,
    "system":    render_system,
    "processes": render_processes,
    "software":  render_software,
}


def render_extended(data: dict):
    section = next(iter(data))
    renderer = SECTION_EXTENDED_RENDERERS.get(section)
    if renderer:
        renderer(data[section])
    else:
        # Fallback to standard render for sections without extended view
        from syslens.display import render
        render(data)
