from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.text import Text
from rich.columns import Columns

console = Console()


def _usage_color(percent):
    if percent < 50:
        return "green"
    elif percent < 80:
        return "yellow"
    return "red"


def _render_system(data):
    s = data["system"]
    text = (
        f"[bold]{s['hostname']}[/bold]  •  "
        f"{s['os']} {s['os_release']} ({s['architecture']})\n"
        f"[dim]{s['os_version']}[/dim]\n"
        f"Uptime: [cyan]{s['uptime']}[/cyan]  •  Boot: [dim]{s['boot_time']}[/dim]  •  "
        f"Python: [cyan]{s['python_version']}[/cyan]"
    )
    console.print(Panel(text, title="[bold blue]System[/bold blue]", border_style="blue"))


def _render_cpu(data):
    cpu = data["cpu"]
    per_core = "  ".join([
        f"C{i}:[{_usage_color(u)}]{u:.0f}%[/{_usage_color(u)}]"
        for i, u in enumerate(cpu["per_core_usage"])
    ])
    lines = [
        f"Cores: [cyan]{cpu['physical_cores']} physical[/cyan] / "
        f"[cyan]{cpu['logical_cores']} logical[/cyan]  •  "
        f"Usage: [{_usage_color(cpu['usage_percent'])}]{cpu['usage_percent']}%[/{_usage_color(cpu['usage_percent'])}]"
    ]
    if "frequency_mhz" in cpu:
        f = cpu["frequency_mhz"]
        lines[0] += f"  •  Freq: [cyan]{f['current']} MHz[/cyan] (max {f['max']} MHz)"
    if "temperature_celsius" in cpu:
        temp = cpu["temperature_celsius"]
        lines[0] += f"  •  Temp: [{_usage_color(temp / 1.0 if temp < 100 else 100)}]{temp}°C[/{_usage_color(temp / 1.0 if temp < 100 else 100)}]"
    lines.append(per_core)
    console.print(Panel("\n".join(lines), title="[bold green]CPU[/bold green]", border_style="green"))


def _render_memory(data):
    mem = data["memory"]
    ram = mem["ram"]
    swap = mem["swap"]
    color = _usage_color(ram["percent"])
    swap_color = _usage_color(swap["percent"])
    text = (
        f"RAM:  [{color}]{ram['used_gb']} / {ram['total_gb']} GB ({ram['percent']}%)[/{color}]  •  "
        f"Available: [cyan]{ram['available_gb']} GB[/cyan]\n"
        f"Swap: [{swap_color}]{swap['used_gb']} / {swap['total_gb']} GB ({swap['percent']}%)[/{swap_color}]  •  "
        f"Free: [cyan]{swap['free_gb']} GB[/cyan]"
    )
    console.print(Panel(text, title="[bold yellow]Memory[/bold yellow]", border_style="yellow"))


def _render_disk(data):
    disk = data["disk"]
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold magenta", padding=(0, 1))
    table.add_column("Device", style="dim")
    table.add_column("Mount")
    table.add_column("FS", style="dim")
    table.add_column("Total", justify="right")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Usage", justify="right")

    for p in disk["partitions"]:
        color = _usage_color(p["percent"])
        table.add_row(
            p["device"], p["mountpoint"], p["fstype"],
            f"{p['total_gb']} GB", f"{p['used_gb']} GB", f"{p['free_gb']} GB",
            f"[{color}]{p['percent']}%[/{color}]",
        )

    content = table
    if disk.get("io_stats"):
        io = disk["io_stats"]
        io_line = (
            f"\nI/O  Read: [cyan]{io['read_gb']} GB[/cyan]  Write: [cyan]{io['write_gb']} GB[/cyan]  "
            f"Ops: [dim]{io['read_count']} reads / {io['write_count']} writes[/dim]"
        )
        from rich.console import Group
        from rich.text import Text
        content = Group(table, Text.from_markup(io_line))

    console.print(Panel(content, title="[bold magenta]Disk[/bold magenta]", border_style="magenta"))


def _render_gpu(data):
    gpus = data["gpu"]["gpus"]
    if not gpus:
        console.print(Panel("[dim]No GPU detected[/dim]", title="[bold red]GPU[/bold red]", border_style="red"))
        return

    lines = []
    for g in gpus:
        parts = [f"[cyan]{g.get('name', 'Unknown')}[/cyan]"]
        if "vram_gb" in g:
            parts.append(f"VRAM: {g['vram_gb']} GB")
        if "vram" in g:
            parts.append(f"VRAM: {g['vram']}")
        if "driver" in g:
            parts.append(f"Driver: [dim]{g['driver']}[/dim]")
        if "vendor" in g:
            parts.append(f"Vendor: [dim]{g['vendor']}[/dim]")
        if "metal" in g:
            parts.append(f"Metal: [dim]{g['metal']}[/dim]")
        lines.append("  •  ".join(parts))

    console.print(Panel("\n".join(lines), title="[bold red]GPU[/bold red]", border_style="red"))


def _render_network(data):
    net = data["network"]
    io = net["io_stats"]
    lines = [
        f"Public IP: [cyan]{net['public_ip']}[/cyan]  •  "
        f"Sent: [cyan]{io['bytes_sent_mb']} MB[/cyan]  Recv: [cyan]{io['bytes_recv_mb']} MB[/cyan]  "
        f"Errors in/out: [dim]{io['errors_in']}/{io['errors_out']}[/dim]",
    ]
    for iface in net["interfaces"]:
        status = "[green]up[/green]" if iface.get("is_up") else "[red]down[/red]"
        speed = f" {iface['speed_mbps']} Mbps" if iface.get("speed_mbps") else ""
        addrs = ", ".join([f"{a['type']}: {a['address']}" for a in iface["addresses"]])
        lines.append(f"  [dim]{iface['name']}[/dim] ({status}{speed})  {addrs}")

    console.print(Panel("\n".join(lines), title="[bold cyan]Network[/bold cyan]", border_style="cyan"))


def _render_battery(data):
    bat = data["battery"]
    if not bat["available"]:
        console.print(Panel("[dim]No battery detected[/dim]", title="[bold]Battery[/bold]", border_style="white"))
        return

    color = _usage_color(100 - bat["percent"])  # low battery = high "usage"
    status = "Plugged in" if bat["plugged_in"] else (
        f"On battery — {bat['time_left_minutes']} min remaining" if bat["time_left_minutes"] else "On battery"
    )
    text = f"[{color}]{bat['percent']}%[/{color}]  •  {status}"
    console.print(Panel(text, title="[bold]Battery[/bold]", border_style="white"))


def _render_software(data):
    installed = data["software"]["installed"]
    if not installed:
        console.print(Panel("[dim]No runtimes detected[/dim]", title="[bold blue]Runtimes[/bold blue]", border_style="blue"))
        return

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Tool", style="cyan bold")
    table.add_column("Version")
    for name, version in installed.items():
        table.add_row(name, version)

    console.print(Panel(table, title="[bold blue]Installed Runtimes[/bold blue]", border_style="blue"))


def _render_processes(data):
    procs = data["processes"]
    console.print(f"\n[bold]Running processes:[/bold] [cyan]{procs['total']}[/cyan]\n")

    cpu_table = Table(title="Top CPU Consumers", box=box.SIMPLE, header_style="bold green", padding=(0, 1))
    cpu_table.add_column("PID", style="dim", justify="right")
    cpu_table.add_column("Name")
    cpu_table.add_column("CPU%", justify="right")
    cpu_table.add_column("MEM%", justify="right")
    cpu_table.add_column("Status", style="dim")
    for p in procs["top_cpu"][:10]:
        cpu_table.add_row(
            str(p["pid"]), p["name"],
            f"[{_usage_color(p['cpu_percent'])}]{p['cpu_percent']:.1f}[/{_usage_color(p['cpu_percent'])}]",
            f"{p['memory_percent']:.2f}",
            p.get("status", ""),
        )

    mem_table = Table(title="Top Memory Consumers", box=box.SIMPLE, header_style="bold yellow", padding=(0, 1))
    mem_table.add_column("PID", style="dim", justify="right")
    mem_table.add_column("Name")
    mem_table.add_column("MEM%", justify="right")
    mem_table.add_column("CPU%", justify="right")
    mem_table.add_column("Status", style="dim")
    for p in procs["top_memory"][:10]:
        mem_table.add_row(
            str(p["pid"]), p["name"],
            f"[{_usage_color(p['memory_percent'] * 5)}]{p['memory_percent']:.2f}[/{_usage_color(p['memory_percent'] * 5)}]",
            f"{p['cpu_percent']:.1f}",
            p.get("status", ""),
        )

    console.print(Columns([cpu_table, mem_table]))


SECTION_RENDERERS = {
    "system": _render_system,
    "cpu": _render_cpu,
    "memory": _render_memory,
    "disk": _render_disk,
    "gpu": _render_gpu,
    "network": _render_network,
    "battery": _render_battery,
    "software": _render_software,
    "processes": _render_processes,
}


def render(data):
    console.print()
    console.rule("[bold cyan]  SYSLENS  [/bold cyan]")
    console.print()

    for section, renderer in SECTION_RENDERERS.items():
        if section in data:
            renderer(data)
            console.print()
