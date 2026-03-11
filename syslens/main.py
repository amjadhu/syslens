import json
from typing import Optional

import typer
from rich.console import Console

from syslens.collectors import cpu, memory, disk, gpu, network, battery, software, processes, system, diagnose
from syslens import commentary, display

app = typer.Typer(
    help="SysLens — Detailed cross-platform system information.",
    add_completion=False,
)
console = Console()

SECTIONS = ["system", "cpu", "memory", "disk", "gpu", "network", "battery", "software", "processes"]


def _collect(sections):
    collectors = {
        "system": system.collect,
        "cpu": cpu.collect,
        "memory": memory.collect,
        "disk": disk.collect,
        "gpu": gpu.collect,
        "network": network.collect,
        "battery": battery.collect,
        "software": software.collect,
        "processes": processes.collect,
    }
    return {s: collectors[s]() for s in sections}


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
):
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
        sections = [section]
    else:
        sections = SECTIONS

    data = _collect(sections)

    if json_output:
        print(json.dumps(data, indent=2, default=str))
    else:
        display.render(data)


if __name__ == "__main__":
    app()
