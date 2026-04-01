#!/usr/bin/env python3
"""
setup.py — Cross-platform setup script for android-log-analysis skills.

Installs:
  - ripgrep (rg)
  - tshark
  - Copies skills to ~/.cline/skills/
  - Copies workflows to global Cline workflows dir (default) or a specific project

Usage:
    python3 setup.py                               # install everything, global workflows
    python3 setup.py --project-dir /path/to/proj  # also install workflows into a project
    python3 setup.py --skip-cli                   # skip rg/tshark install, just copy files

Global workflow locations (auto-detected):
  macOS/Linux: ~/Documents/Cline/Workflows/
  Windows:     ~\\Documents\\Cline\\Workflows\\
"""

import os
import sys
import shutil
import platform
import subprocess
import argparse


SKILLS = ["android-log-analysis", "android-pcap-analysis", "template-engine", "workflow-orchestrator", "postprocessors", "log-template-creator", "pcap-template-creator", "workflow-creator"]
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SKILLS_SRC = os.path.join(REPO_ROOT, "skills")
WORKFLOWS_SRC = os.path.join(REPO_ROOT, "skills", "workflow-creator", "examples")

# Shared Python modules copied into workflow-orchestrator/scripts/ so the
# deployed skill can import them without needing the repo on sys.path.
SHARED_MODULES = ["yaml_utils.py", "config.py", "workflow_config.yaml"]


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd, check=True):
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str))
    if check and result.returncode != 0:
        print(f"  [WARN] command exited with code {result.returncode}")
    return result.returncode == 0


def is_installed(binary):
    return shutil.which(binary) is not None


def cline_skills_dir():
    return os.path.join(os.path.expanduser("~"), ".cline", "skills")


def global_workflows_dir():
    """Cline global workflows directory (cross-platform)."""
    return os.path.join(os.path.expanduser("~"), "Documents", "Cline", "Workflows")


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def ok(msg):   print(f"  ✓  {msg}")
def info(msg): print(f"  →  {msg}")
def warn(msg): print(f"  !  {msg}")
def fail(msg): print(f"  ✗  {msg}")


# ── CLI install ───────────────────────────────────────────────────────────────

def install_ripgrep():
    if is_installed("rg"):
        ok("ripgrep already installed")
        return True

    info("Installing ripgrep...")
    system = platform.system()

    if system == "Darwin":
        return run(["brew", "install", "ripgrep"])
    elif system == "Linux":
        distro = _linux_distro()
        if distro in ("ubuntu", "debian"):
            run(["sudo", "apt-get", "update", "-qq"])
            return run(["sudo", "apt-get", "install", "-y", "ripgrep"])
        elif distro in ("fedora", "rhel", "centos"):
            return run(["sudo", "dnf", "install", "-y", "ripgrep"])
        elif distro == "arch":
            return run(["sudo", "pacman", "-Sy", "--noconfirm", "ripgrep"])
        else:
            fail(f"Unknown Linux distro '{distro}'. Install ripgrep manually:")
            print("    https://github.com/BurntSushi/ripgrep#installation")
            return False
    elif system == "Windows":
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
    else:
        fail(f"Unsupported OS: {system}")
        return False


def install_tshark():
    if is_installed("tshark"):
        ok("tshark already installed")
        return True

    info("Installing tshark...")
    system = platform.system()

    if system == "Darwin":
        return run(["brew", "install", "wireshark"])
    elif system == "Linux":
        distro = _linux_distro()
        if distro in ("ubuntu", "debian"):
            run(["sudo", "apt-get", "update", "-qq"])
            # Pre-answer the tshark non-root capture question
            run(["bash", "-c",
                 "echo 'wireshark-common wireshark-common/install-setuid boolean true' "
                 "| sudo debconf-set-selections"])
            return run(["sudo", "apt-get", "install", "-y", "tshark"])
        elif distro in ("fedora", "rhel", "centos"):
            return run(["sudo", "dnf", "install", "-y", "wireshark-cli"])
        elif distro == "arch":
            return run(["sudo", "pacman", "-Sy", "--noconfirm", "wireshark-cli"])
        else:
            fail(f"Unknown Linux distro '{distro}'. Install tshark manually:")
            print("    https://www.wireshark.org/download.html")
            return False
    elif system == "Windows":
        if is_installed("winget"):
            return run(["winget", "install", "WiresharkFoundation.Wireshark", "--silent"])
        elif is_installed("choco"):
            return run(["choco", "install", "wireshark", "-y"])
        else:
            fail("No package manager found (winget/choco).")
            print("    Install Wireshark (includes tshark): https://www.wireshark.org/download.html")
            return False
    else:
        fail(f"Unsupported OS: {system}")
        return False


def _linux_distro():
    """Detect Linux distro from /etc/os-release."""
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("ID="):
                    return line.strip().split("=")[1].strip('"').lower()
    except FileNotFoundError:
        pass
    return "unknown"


def install_python_deps():
    section("Python dependencies")
    try:
        import yaml  # noqa: F401
        ok("PyYAML already installed")
    except ImportError:
        info("Installing PyYAML...")
        run([sys.executable, "-m", "pip", "install", "PyYAML"])


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
        ok(f"Installed skill: {skill} → {dst}")

    # Copy shared Python modules into every skill's scripts/ dir so each script
    # can be invoked standalone and find its dependencies immediately.
    for skill in SKILLS:
        scripts_dir = os.path.join(dest_base, skill, "scripts")
        if os.path.isdir(scripts_dir):
            for mod in SHARED_MODULES:
                src = os.path.join(REPO_ROOT, mod)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(scripts_dir, mod))
    ok("Copied shared modules to all skill script dirs")


def install_workflows(dest):
    """Copy workflow files to dest directory."""
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

    ok(f"Installed workflows → {dest}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Set up android log analysis skills and workflows."
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="Also install workflows into this project's .clinerules/workflows/ directory"
    )
    parser.add_argument(
        "--skip-cli",
        action="store_true",
        help="Skip ripgrep and tshark installation"
    )
    args = parser.parse_args()

    print(f"\n  Android Log & PCAP Analysis — Setup")
    print(f"  Platform: {platform.system()} {platform.machine()}")
    print(f"  Python:   {sys.version.split()[0]}")

    errors = []

    if not args.skip_cli:
        section("Installing CLI tools")
        if not install_ripgrep():
            errors.append("ripgrep install failed — log analysis workflows will not work")
        if not install_tshark():
            errors.append("tshark install failed — PCAP analysis workflows will not work")

    # Python dependencies (PyYAML etc.) are now caller-managed.
    install_python_deps()

    section("Installing Cline skills")
    install_skills()

    section("Installing workflows (global)")
    global_dest = global_workflows_dir()
    install_workflows(global_dest)

    if args.project_dir:
        section(f"Installing workflows (project: {args.project_dir})")
        project_dest = os.path.join(args.project_dir, ".clinerules", "workflows")
        install_workflows(project_dest)

    section("Verification")
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

    if os.path.isdir(global_dest):
        count = len([f for f in os.listdir(global_dest) if f.endswith(".md")])
        ok(f"global workflows: {count} workflow(s) in {global_dest}")
    else:
        fail(f"global workflows directory missing: {global_dest}")
        errors.append("global workflows not installed")

    print()
    if errors:
        print("  Setup completed with warnings:")
        for e in errors:
            warn(e)
    else:
        print("  Setup complete. Open any project in VS Code with Cline and try:")
        print("    /battery-troubleshooting.md")
        print("    /emergency-call-troubleshooting.md")
        print("    /ims-pcap-troubleshooting.md")
    print()


if __name__ == "__main__":
    main()
