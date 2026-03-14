# SysLens

A cross-platform CLI for detailed system information and diagnostics. Get a rich overview of your hardware and software in seconds — or drill deep into any individual section.

## Features

- Full system overview: CPU, memory, disk, GPU, network, battery, software, processes
- Extended detail per section (cache levels, DIMM slots, SMART health, WiFi signal, etc.)
- System health diagnostics from Windows Event Log + heuristic checks
- Optional AI-powered commentary on events via Claude API
- JSON output mode for scripting/automation

## Install

```bash
git clone https://github.com/yourusername/syslens
cd syslens
pip install -e .
```

For AI-powered diagnostics (optional):
```bash
pip install -e ".[ai]"
```

## Usage

### Full system overview
```bash
syslens
```

### Extended detail for a single section
```bash
syslens --section cpu
syslens --section memory
syslens --section disk
syslens --section gpu
syslens --section network
syslens --section battery
syslens --section system
syslens --section software
syslens --section processes
```

### System health diagnostics
```bash
syslens --diagnose

# With AI commentary (requires Anthropic API key)
syslens --diagnose --api-key sk-ant-...
# Or set the env var:
export ANTHROPIC_API_KEY=sk-ant-...
syslens --diagnose
```

### JSON output
Any command can output JSON:
```bash
syslens --json
syslens --section disk --json
syslens --diagnose --json
```

## What Each Section Shows

| Section | Standard | Extended |
|---------|----------|---------|
| **system** | OS, hostname, uptime, boot time | BIOS/board info, SecureBoot, TPM |
| **cpu** | Usage %, cores, frequency, temp | L1/L2/L3 cache, virtualization, power plan, per-core freq |
| **memory** | RAM/swap used/total | DIMM slots, speed, capacity, manufacturer |
| **disk** | Partitions, usage %, I/O stats | SMART health, physical drives, top 5 folders by size |
| **gpu** | GPU name, VRAM | DirectX version, connected displays, driver date |
| **network** | Interfaces, IP, I/O stats | WiFi SSID/channel/signal, DNS, gateway, routing |
| **battery** | Charge %, status, time remaining | Wear %, cycle count, charge rate, chemistry |
| **software** | Installed runtimes + versions | pip packages (outdated), npm global, env vars, PATH |
| **processes** | Top 10 by CPU/memory | Top 15 by CPU/memory, threads, user, start time, cmdline |

## Diagnostics (`--diagnose`)

Scans the last 24 hours of system events and runs heuristic checks:

- **Windows**: queries System and Application event logs via PowerShell
- **macOS**: parses `log show` output and crash reports
- **Heuristics**: disk space, high RAM usage, network errors, CPU-heavy processes

Events are categorized (driver issues, disk errors, service failures, app crashes) and annotated with:
1. A built-in knowledge base of 100+ Windows Event IDs with actionable advice
2. Claude AI commentary for unknown events (if API key is provided)

## Platform Support

| Feature | Windows | macOS | Linux |
|---------|---------|-------|-------|
| Basic overview | Full | Full | Full |
| Extended sections | Full | Partial | Minimal |
| `--diagnose` | Full | Partial | - |

## Requirements

- Python 3.9+
- `psutil`, `rich`, `typer` (installed automatically)
- `anthropic` (optional, for `--diagnose` with AI commentary)
