import json
from typing import Optional

import typer
from rich.console import Console

from syslens.collectors import cpu, memory, disk, gpu, network, battery, software, processes, system, diagnose, stack_dump, reboot
from syslens.collectors.extended import (
    gpu as gpu_ext, cpu as cpu_ext, memory as memory_ext,
    disk as disk_ext, network as network_ext,
    battery as battery_ext, system as system_ext,
    processes as processes_ext, software as software_ext,
)
from syslens import commentary, display, display_extended

app = typer.Typer(
    help="SysLens — Detailed cross-platform system information.",
    add_completion=False,
)
console = Console()

SECTIONS = ["system", "cpu", "memory", "disk", "gpu", "network", "battery", "software", "processes"]


COLLECTORS = {
    "system":    system.collect,
    "cpu":       cpu.collect,
    "memory":    memory.collect,
    "disk":      disk.collect,
    "gpu":       gpu.collect,
    "network":   network.collect,
    "battery":   battery.collect,
    "software":  software.collect,
    "processes": processes.collect,
}

COLLECTORS_EXTENDED = {
    "system":  system_ext.collect_extended,
    "cpu":     cpu_ext.collect_extended,
    "memory":  memory_ext.collect_extended,
    "disk":    disk_ext.collect_extended,
    "gpu":     gpu_ext.collect_extended,
    "network": network_ext.collect_extended,
    "battery": battery_ext.collect_extended,
    "software":  software_ext.collect_extended,
    "processes": processes_ext.collect_extended,
}


def _collect(sections, extended=False):
    pool = COLLECTORS_EXTENDED if extended else COLLECTORS
    return {s: pool[s]() for s in sections}


@app.command()
def main(
    json_output:   bool = typer.Option(False, "--json",     "-j", help="Output as JSON"),
    run_diagnose:  bool = typer.Option(False, "--diagnose", "-d", help="Run system diagnostic report"),
    section: Optional[str] = typer.Option(
        None, "--section", "-s",
        help=f"Show only one section: {', '.join(SECTIONS)}"
    ),
    api_key: Optional[str] = typer.Option(
        None, "--api-key",
        help="Anthropic API key for AI commentary on unknown events (falls back to ANTHROPIC_API_KEY env var).",
        envvar="ANTHROPIC_API_KEY",
        show_default=False,
        hide_input=True,
    ),
    dump: Optional[str] = typer.Option(
        None, "--dump",
        help="Dump stack trace for a process. Accepts a PID or process name.",
        show_default=False,
    ),
    show_reboot: bool = typer.Option(False, "--reboot", "-r", help="Show why the system last restarted"),
):
    if show_reboot:
        reboot_data = reboot.collect()
        if json_output:
            print(json.dumps(reboot_data, indent=2, default=str))
        else:
            display.render_reboot(reboot_data)
        raise typer.Exit(0)

    if dump is not None:
        dump_data = stack_dump.collect_dump(dump)
        if json_output:
            print(json.dumps(dump_data, indent=2, default=str))
        else:
            display.render_dump(dump_data)
        raise typer.Exit(0)

    if run_diagnose:
        diag_data = diagnose.collect()
        diag_data = commentary.annotate(diag_data, api_key=api_key)
        if json_output:
            print(json.dumps(diag_data, indent=2, default=str))
        else:
            display.render_diagnose(diag_data)
        raise typer.Exit(0)

    if section:
        if section not in SECTIONS:
            console.print(f"[red]Unknown section '{section}'. Choose from: {', '.join(SECTIONS)}[/red]")
            raise typer.Exit(1)
        data = _collect([section], extended=True)
        if json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            display_extended.render_extended(data)
    else:
        data = _collect(SECTIONS)
        if json_output:
            print(json.dumps(data, indent=2, default=str))
        else:
            display.render(data)


if __name__ == "__main__":
    app()
