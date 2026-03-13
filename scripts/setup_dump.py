#!/usr/bin/env python3
"""
setup_dump.py — one-shot setup for `syslens --dump`

Run with:
    python scripts/setup_dump.py

What it does
------------
1. Installs py-spy  (Python process stack traces, all platforms)
2. Windows only:
   a. Installs WinDbg via winget  (native stack traces for any process)
   b. Sets _NT_SYMBOL_PATH permanently for the current user so that
      Windows system DLL exports resolve to full function names
"""

import os
import platform
import subprocess
import sys


def _run(cmd, **kwargs):
    return subprocess.run(cmd, **kwargs)


def _pip_install(package):
    print(f"  pip install {package} ...", end=" ", flush=True)
    r = _run([sys.executable, "-m", "pip", "install", package],
             capture_output=True, text=True)
    if r.returncode == 0:
        print("ok")
    else:
        print("FAILED")
        print(r.stderr.strip())


def _winget_install(package_id):
    print(f"  winget install {package_id} ...", end=" ", flush=True)
    r = _run(["winget", "install", "--accept-package-agreements",
               "--accept-source-agreements", package_id],
             capture_output=True, text=True)
    if r.returncode == 0:
        print("ok")
    else:
        # winget exit code 0x8A150015 means "already installed"
        if "already installed" in (r.stdout + r.stderr).lower():
            print("already installed")
        else:
            print("FAILED")
            print((r.stdout + r.stderr).strip()[:300])


def _set_user_env(name, value):
    """Persist a user environment variable via PowerShell (Windows)."""
    print(f"  Setting {name} ...", end=" ", flush=True)
    script = (
        f"[System.Environment]::SetEnvironmentVariable("
        f"'{name}', '{value}', 'User')"
    )
    r = _run(["powershell", "-NoProfile", "-Command", script],
             capture_output=True, text=True)
    if r.returncode == 0:
        print("ok")
    else:
        print("FAILED")
        print(r.stderr.strip())


def _check_user_env(name):
    r = _run(["powershell", "-NoProfile", "-Command",
               f"[System.Environment]::GetEnvironmentVariable('{name}', 'User')"],
             capture_output=True, text=True)
    return (r.stdout or "").strip()


def main():
    print("=== syslens --dump setup ===\n")

    # ── 1. py-spy (all platforms) ─────────────────────────────────────────────
    print("[1/3] py-spy  (Python process stack traces)")
    _pip_install("py-spy")

    if platform.system() != "Windows":
        print("\nNon-Windows: only py-spy is needed.")
        print("\nDone. Try:  syslens --dump <pid|name>")
        return

    # ── 2. WinDbg Preview (Windows) ───────────────────────────────────────────
    print("\n[2/3] WinDbg Preview  (native stack traces for any process)")
    _winget_install("Microsoft.WinDbg")
    print("      Note: WinDbg Preview installs GUI-only stubs. For full")
    print("      command-line native symbols, install Windows SDK Debugging")
    print("      Tools: winget install Microsoft.WindowsSDK.10.0.26100")
    print("      That places cdb.exe in:")
    print("        C:\\Program Files (x86)\\Windows Kits\\10\\Debuggers\\x64\\")

    # ── 3. _NT_SYMBOL_PATH ────────────────────────────────────────────────────
    print("\n[3/3] _NT_SYMBOL_PATH  (Microsoft public symbol server)")
    sym_path = "srv*C:\\Symbols*https://msdl.microsoft.com/download/symbols"
    existing = _check_user_env("_NT_SYMBOL_PATH")
    if existing:
        print(f"  Already set: {existing}")
    else:
        _set_user_env("_NT_SYMBOL_PATH", sym_path)
        print(f"  Value: {sym_path}")
        print("  Symbols will be cached in C:\\Symbols on first use.")
        print("  Open a NEW terminal for this to take effect.")

    print("\n=== Summary ===")
    print("  py-spy          → Python process stacks (any process as same user)")
    print("  DbgHelp.dll     → Native stacks via PE export tables (built-in,")
    print("                    no install needed; resolves exported fn names)")
    print("  _NT_SYMBOL_PATH → Would enable full PDB symbols if using the SDK")
    print("                    cdb.exe instead of the system DbgHelp")
    print("\nTry it:")
    print("  syslens --dump <pid>")
    print("  syslens --dump notepad.exe")
    print("  syslens --dump python")


if __name__ == "__main__":
    main()
