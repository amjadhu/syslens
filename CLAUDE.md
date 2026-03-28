# SysLens — Claude Code Context

## What This Project Is
A cross-platform CLI tool for detailed system information and diagnostics. Built with Python, Rich, Typer, and psutil.

## How to Run
```bash
syslens                          # full system overview
syslens --section <name>         # extended detail for one section
syslens --diagnose               # event log + heuristic health check
syslens --diagnose --api-key sk-... # same + Claude AI commentary
syslens --dump <pid|name>        # stack dump for a process
syslens --reboot                 # show why the system last restarted
syslens --json                   # any mode as JSON output
```

Section names: `system`, `cpu`, `memory`, `disk`, `gpu`, `network`, `battery`, `software`, `processes`

## Install (dev mode)
```bash
pip install -e .           # core
pip install -e ".[ai]"     # + Anthropic SDK for --diagnose AI commentary
pip install -e ".[dump]"   # + py-spy for Python process stack traces
```

### Setting up --dump on a new machine
```bash
python scripts/setup_dump.py
```
This installs py-spy, WinDbg (Windows), and sets `_NT_SYMBOL_PATH`. Open a new terminal after running it.

**Symbol resolution tiers for `--dump` (best → fallback):**
| Method | Gives you | Requires |
|--------|-----------|----------|
| py-spy | Python-level frames with file + line | `pip install py-spy` |
| cdb.exe | Full native stacks + PDB symbols | Windows SDK Debugging Tools |
| DbgHelp.dll + PE exports | Native stacks, exported fn names | nothing (built into Windows) |
| psutil threads | Thread IDs + CPU time only | nothing |

## Architecture

### Data Flow
```
CLI flag → main.py → collector(s) → display renderer → Rich terminal output
                                  → (optional) JSON dump
```

### Two-Tier Collectors
- **Basic** (`syslens/collectors/`): Fast (~0.5s), cross-platform, psutil-based. Used for the default full overview.
- **Extended** (`syslens/collectors/extended/`): Slower, platform-specific (Windows WMI / macOS sysctl). Only run when `--section` is specified.

### Routing in `main.py`
- `COLLECTORS` dict maps section names → basic collector functions
- `COLLECTORS_EXTENDED` dict maps section names → extended collector functions
- `display.render(data)` handles full overview
- `display_extended.SECTION_EXTENDED_RENDERERS[section](data)` handles single-section view

### Commentary System (`syslens/commentary/`)
Used only with `--diagnose`. Two-layer fallback:
1. **Static KB** (`knowledge_base.py`): ~100+ Windows Event IDs with concern levels and actions — instant, no API needed
2. **Claude API** (`engine.py`): Batches unknown events to Claude Haiku for AI commentary — requires `--api-key` or `ANTHROPIC_API_KEY` env var

## Key Files
| File | Purpose |
|------|---------|
| `syslens/main.py` | CLI entry, collector routing, flag handling |
| `syslens/display.py` | Rich rendering for full overview (all 9 sections) |
| `syslens/display_extended.py` | Rich rendering for single-section extended detail |
| `syslens/collectors/diagnose.py` | Windows Event Log + heuristic health checks |
| `syslens/collectors/reboot.py` | Last restart reason collector (Event IDs 41, 1074, 6005, 6006, 6008) |
| `syslens/collectors/stack_dump.py` | Process stack trace collector (py-spy / DbgHelp / gdb / lldb) |
| `syslens/commentary/engine.py` | Static KB lookup + Claude API fallback |
| `syslens/commentary/knowledge_base.py` | Windows Event ID → commentary mappings |
| `scripts/setup_dump.py` | One-shot setup script for `--dump` dependencies |
| `pyproject.toml` | Build config, deps, entry point |

## Sections & Their Extended Collectors
| Section | Extended collector highlights |
|---------|-------------------------------|
| cpu | Cache L1/L2/L3, virtualization, power plan, per-core freq |
| memory | DIMM slots, speed, capacity, manufacturer |
| disk | SMART health, physical drives, partitions |
| gpu | DirectX version, connected displays |
| network | WiFi SSID/channel/signal, DNS, gateway, routing |
| battery | Wear %, cycle count, charge rate, chemistry |
| system | BIOS/board info, SecureBoot, TPM version |
| processes | Top 15 by CPU + memory, threads, user, start time, cmdline |
| software | pip packages (outdated flag), npm global, env vars, PATH |

## Adding a New Section
1. Create `syslens/collectors/<section>.py` with a `collect()` function
2. Create `syslens/collectors/extended/<section>.py` with a `collect_extended()` function
3. Add a `render_<section>(data)` function in `display.py` (standard) and `display_extended.py` (extended)
4. Wire up in `main.py`: add to `SECTIONS`, `COLLECTORS`, `COLLECTORS_EXTENDED`
5. Add to `SECTION_EXTENDED_RENDERERS` in `display_extended.py`

## Platform Notes
- Windows: WMI via `wmic` or PowerShell for most extended collectors
- macOS: `system_profiler`, `sysctl`, `pmset` for extended collectors
- Linux: partial support in basic collectors; extended collectors mostly unsupported

## Dependencies
- `psutil` — system metrics
- `rich` — terminal UI
- `typer` — CLI framework
- `anthropic` (optional) — AI commentary in `--diagnose`
- `py-spy` (optional) — Python process stack traces in `--dump`
