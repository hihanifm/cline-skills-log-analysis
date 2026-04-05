#!/usr/bin/env python3
"""
windows_installer.py — Windows .exe installer for android-log-analysis skills.

Double-click the built .exe to:
  - Install ripgrep and tshark (via winget/scoop/choco)
  - Install PyYAML into system Python
  - Copy skills to ~/.cline/skills/
  - Copy workflows to ~/Documents/Cline/Workflows/

Build this into a .exe by running build_windows_exe.bat on a Windows machine.
"""

import os
import sys
import shutil
import platform
import subprocess


SKILLS = [
    "android-log-analysis",
    "android-pcap-analysis",
    "template-engine",
    "workflow-orchestrator",
    "postprocessors",
    "log-template-creator",
    "pcap-template-creator",
    "workflow-creator",
    "template-library",
]

SKILL_SHARED_MODULES = {
    "template-engine":       ["yaml_utils.py"],
    "workflow-orchestrator": ["yaml_utils.py", "config.py", "workflow_config.yaml"],
}

# When frozen by PyInstaller, data files are unpacked to sys._MEIPASS.
# In dev mode (running as a plain .py), use the script's own directory.
if getattr(sys, "frozen", False):
    DATA_ROOT = sys._MEIPASS
else:
    DATA_ROOT = os.path.dirname(os.path.abspath(__file__))

SKILLS_SRC = os.path.join(DATA_ROOT, "skills")
WORKFLOWS_SRC = os.path.join(DATA_ROOT, "skills", "workflow-creator", "examples")

_version_file = os.path.join(DATA_ROOT, "VERSION")
VERSION = open(_version_file).read().strip() if os.path.isfile(_version_file) else "dev"


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd):
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str))
    if result.returncode != 0:
        print(f"  [WARN] command exited with code {result.returncode}")
    return result.returncode == 0


def is_installed(binary):
    return shutil.which(binary) is not None


def cline_skills_dir():
    return os.path.join(os.path.expanduser("~"), ".cline", "skills")


def global_workflows_dir():
    return os.path.join(os.path.expanduser("~"), "Documents", "Cline", "Workflows")


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def ok(msg):   print(f"  OK  {msg}")
def info(msg): print(f"  ->  {msg}")
def warn(msg): print(f"  !   {msg}")
def fail(msg): print(f"  X   {msg}")


# ── CLI install (Windows only) ────────────────────────────────────────────────

def install_ripgrep():
    if is_installed("rg"):
        ok("ripgrep already installed")
        return True

    info("Installing ripgrep...")
    if is_installed("winget"):
        return run(["winget", "install", "BurntSushi.ripgrep.MSVC", "--silent"])
    elif is_installed("scoop"):
        return run(["scoop", "install", "ripgrep"])
    elif is_installed("choco"):
        return run(["choco", "install", "ripgrep", "-y"])
    else:
        fail("No package manager found (winget/scoop/choco).")
        print("    Install ripgrep manually: https://github.com/BurntSushi/ripgrep/releases")
        return False


def install_tshark():
    if is_installed("tshark"):
        ok("tshark already installed")
        return True

    info("Installing Wireshark (includes tshark)...")
    if is_installed("winget"):
        return run(["winget", "install", "WiresharkFoundation.Wireshark", "--silent"])
    elif is_installed("choco"):
        return run(["choco", "install", "wireshark", "-y"])
    else:
        fail("No package manager found (winget/choco).")
        print("    Install Wireshark manually: https://www.wireshark.org/download.html")
        return False


# ── Python dependency ─────────────────────────────────────────────────────────

def find_system_python():
    """
    sys.executable inside a frozen .exe points to the PyInstaller bootstrap,
    not system Python. Search PATH for a real Python interpreter instead.
    """
    for cmd in ["py", "python3", "python"]:
        path = shutil.which(cmd)
        if path:
            return path
    return None


def install_pyyaml():
    section("Python dependencies")
    py = find_system_python()
    if py is None:
        warn("No Python interpreter found in PATH — skipping PyYAML install.")
        warn("The skill scripts require Python 3 and PyYAML. Install Python from python.org.")
        return

    # Check if PyYAML is already present in system Python.
    result = subprocess.run([py, "-c", "import yaml"], capture_output=True)
    if result.returncode == 0:
        ok("PyYAML already installed")
        return

    info(f"Installing PyYAML via {py} ...")
    run([py, "-m", "pip", "install", "PyYAML"])


# ── File installation ─────────────────────────────────────────────────────────

def install_skills():
    dest_base = cline_skills_dir()
    os.makedirs(dest_base, exist_ok=True)

    for skill in SKILLS:
        src = os.path.join(SKILLS_SRC, skill)
        dst = os.path.join(dest_base, skill)
        if not os.path.isdir(src):
            fail(f"Skill source not found: {src}")
            continue
        if os.path.exists(dst):
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        ok(f"Installed skill: {skill}")

    # Copy shared Python modules into the skill script dirs that need them.
    for skill, modules in SKILL_SHARED_MODULES.items():
        scripts_dir = os.path.join(dest_base, skill, "scripts")
        if os.path.isdir(scripts_dir):
            for mod in modules:
                src = os.path.join(DATA_ROOT, mod)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(scripts_dir, mod))
    ok("Copied shared modules to skill script dirs")


def install_workflows():
    dest = global_workflows_dir()
    os.makedirs(dest, exist_ok=True)

    for item in os.listdir(WORKFLOWS_SRC):
        src = os.path.join(WORKFLOWS_SRC, item)
        dst = os.path.join(dest, item)
        if os.path.isdir(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    ok(f"Installed workflows -> {dest}")


# ── Verification ──────────────────────────────────────────────────────────────

def verify():
    section("Verification")
    errors = []

    for binary, label in [("rg", "ripgrep"), ("tshark", "tshark")]:
        if is_installed(binary):
            result = subprocess.run([binary, "--version"], capture_output=True, text=True)
            version = result.stdout.splitlines()[0] if result.stdout else "unknown"
            ok(f"{label}: {version}")
        else:
            warn(f"{label}: not found in PATH")

    skills_dir = cline_skills_dir()
    for skill in SKILLS:
        path = os.path.join(skills_dir, skill, "SKILL.md")
        if os.path.isfile(path):
            ok(f"skill installed: {skill}")
        else:
            fail(f"skill missing: {skill}")
            errors.append(f"skill not installed: {skill}")

    wo_agent = os.path.join(skills_dir, "workflow-orchestrator", "scripts", "context_builder_agent.py")
    if os.path.isfile(wo_agent):
        ok("workflow-orchestrator agents deployed")
    else:
        fail("workflow-orchestrator agents missing")
        errors.append("workflow-orchestrator agents not deployed")

    wf_dir = global_workflows_dir()
    if os.path.isdir(wf_dir):
        count = len([f for f in os.listdir(wf_dir) if f.endswith(".md")])
        ok(f"global workflows: {count} workflow(s) in {wf_dir}")
    else:
        fail(f"global workflows directory missing: {wf_dir}")
        errors.append("global workflows not installed")

    return errors


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print(f"  Android Log & PCAP Analysis — Windows Installer v{VERSION}")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print()

    errors = []

    section("Installing CLI tools")
    if not install_ripgrep():
        errors.append("ripgrep install failed — log analysis workflows will not work")
    if not install_tshark():
        errors.append("tshark install failed — PCAP analysis workflows will not work")

    install_pyyaml()

    section("Installing Cline skills")
    install_skills()

    section("Installing workflows")
    install_workflows()

    errors += verify()

    print()
    if errors:
        print("  Setup completed with warnings:")
        for e in errors:
            warn(e)
    else:
        print("  Setup complete! Open any project in VS Code with Cline and try:")
        print("    /battery-troubleshooting.md")
        print("    /emergency-call-troubleshooting.md")
        print("    /ims-pcap-troubleshooting.md")
    print()
    input("Press Enter to close...")


if __name__ == "__main__":
    main()
