import json
import os
import shutil
import subprocess
import sys
from syslens.collectors.software import collect as collect_basic, RUNTIMES


def _run(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=timeout, encoding="utf-8", errors="replace")
        return result.stdout.strip()
    except Exception:
        return ""


def _pip_packages():
    python = shutil.which("python") or shutil.which("python3") or sys.executable
    out = _run([python, "-m", "pip", "list", "--format=json"], timeout=15)
    if not out:
        return []
    try:
        return json.loads(out)  # [{"name": "...", "version": "..."}]
    except json.JSONDecodeError:
        return []


def _pip_outdated():
    python = shutil.which("python") or shutil.which("python3") or sys.executable
    out = _run([python, "-m", "pip", "list", "--outdated", "--format=json"], timeout=20)
    if not out:
        return []
    try:
        return json.loads(out)  # [{"name": "...", "version": "...", "latest_version": "..."}]
    except json.JSONDecodeError:
        return []


def _npm_global_packages():
    npm = shutil.which("npm")
    if not npm:
        return {}
    out = _run([npm, "list", "-g", "--json", "--depth=0"], timeout=15)
    if not out:
        return {}
    try:
        data = json.loads(out)
        deps = data.get("dependencies", {})
        return {name: info.get("version", "N/A") for name, info in deps.items()}
    except json.JSONDecodeError:
        return {}


def _runtime_paths():
    paths = {}
    for name, cmd in RUNTIMES.items():
        exe = shutil.which(cmd[0])
        if exe:
            paths[name] = exe
    return paths


def _env_vars():
    keys_of_interest = [
        "PYTHONPATH", "PYTHONHOME",
        "NODE_PATH", "NODE_ENV",
        "GOPATH", "GOROOT",
        "JAVA_HOME", "ANDROID_HOME",
        "RUSTUP_HOME", "CARGO_HOME",
        "VIRTUAL_ENV", "CONDA_DEFAULT_ENV",
        "AWS_PROFILE", "KUBECONFIG",
    ]
    result = {}
    for key in keys_of_interest:
        val = os.environ.get(key)
        if val:
            result[key] = val
    return result


def _path_entries():
    path = os.environ.get("PATH", "")
    sep = ";" if os.name == "nt" else ":"
    entries = [p.strip() for p in path.split(sep) if p.strip()]
    return entries


def collect_extended():
    basic = collect_basic()
    paths = _runtime_paths()

    # Enrich installed runtimes with paths
    installed = {}
    for name, version in basic["installed"].items():
        installed[name] = {
            "version": version,
            "path": paths.get(name, "N/A"),
        }

    pip_pkgs    = _pip_packages()
    pip_outdated = _pip_outdated()
    npm_pkgs    = _npm_global_packages()
    env_vars    = _env_vars()
    path_entries = _path_entries()

    return {
        "installed":       installed,
        "pip_packages":    pip_pkgs,
        "pip_outdated":    pip_outdated,
        "npm_global":      npm_pkgs,
        "env_vars":        env_vars,
        "path_entries":    path_entries,
    }
