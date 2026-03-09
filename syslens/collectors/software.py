import subprocess
import shutil

RUNTIMES = {
    "python": ["python", "--version"],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "bun": ["bun", "--version"],
    "go": ["go", "version"],
    "rust": ["rustc", "--version"],
    "java": ["java", "--version"],
    "git": ["git", "--version"],
    "docker": ["docker", "--version"],
    "kubectl": ["kubectl", "version", "--client"],
    "terraform": ["terraform", "--version"],
    "aws": ["aws", "--version"],
}


def _get_version(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        output = (result.stdout or result.stderr).strip()
        return output.split("\n")[0] if output else None
    except Exception:
        return None


def collect():
    installed = {}
    for name, cmd in RUNTIMES.items():
        if shutil.which(cmd[0]):
            version = _get_version(cmd)
            if version:
                installed[name] = version
    return {"installed": installed}
