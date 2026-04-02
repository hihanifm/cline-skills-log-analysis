"""
template_runner.py — Apply a template YAML to a log or pcap file.

Importable module used by context_builder_agent.py.
Can also be run directly as a CLI tool.

Usage (library):
    from template_runner import load_template, resolve_patterns, run_template, run_patterns

Usage (CLI):
    python3 template_runner.py \
        --template /path/to/wakelock.yaml \
        --file /path/to/logcat.txt \
        [--skill android-log-analysis] \
        [--max-lines 200]
"""

import importlib.util
import os
import sys
from typing import Optional

# Add shared modules dir to sys.path (same walker pattern as the agent scripts).
def _find_shared_modules_dir():
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isfile(os.path.join(d, "yaml_utils.py")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            raise ImportError("Cannot find yaml_utils.py. Run setup.py to install.")
        d = parent

_SHARED = _find_shared_modules_dir()
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import yaml_utils

# Template search dirs — templates live in the template-library skill, not here.
# Deployed: ~/.cline/skills/template-library/templates/
# Dev:      <repo>/skills/template-library/templates/
_LIB_ROOT_DEPLOYED = os.path.join(
    os.path.expanduser("~"), ".cline", "skills", "template-library"
)
_LIB_ROOT_DEV = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..", "template-library"
)
_SKILL_TEMPLATE_DIRS = [
    os.path.join(_LIB_ROOT_DEPLOYED, "templates"),
    os.path.normpath(os.path.join(_LIB_ROOT_DEV, "templates")),
]


def _project_template_dirs(base_dir: str) -> list:
    """
    Infer project-local templates/ dir from the workflow file's location.
    When a workflow lives at <project>/.clinerules/workflows/<name>.md,
    walking up two levels reaches the project root, which may have a
    templates/ directory committed to the repo.
    Returns a list of candidate paths (may not exist).
    """
    dirs = []
    d = base_dir
    for _ in range(4):
        candidate = os.path.join(d, "log-templates")
        if os.path.isdir(candidate):
            dirs.append(candidate)
            break
        d = os.path.dirname(d)
        if d == os.path.dirname(d):
            break
    return dirs


# ── Skill module loader ───────────────────────────────────────────────────────

def load_skill_module(skill_name: str, module_name: str):
    """
    Dynamically import a skill module from ~/.cline/skills/<skill>/scripts/<module>.py.
    Falls back to repo-relative path for dev mode.
    """
    skill_dir = os.path.join(os.path.expanduser("~"), ".cline", "skills", skill_name, "scripts")
    module_path = os.path.join(skill_dir, f"{module_name}.py")

    if not os.path.isfile(module_path):
        # Dev fallback: _SHARED is the repo root in dev mode
        module_path = os.path.join(_SHARED, "skills", skill_name, "scripts", f"{module_name}.py")

    if not os.path.isfile(module_path):
        raise ImportError(
            f"Cannot find {module_name}.py for skill '{skill_name}'. "
            f"Run setup.py to install skills first."
        )

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Template loading ──────────────────────────────────────────────────────────

def load_template(path: str, base_dir: str = "", errors: list = None) -> list:
    """
    Load a template YAML file and return its list of template entries.

    Resolution order for relative paths:
      1. Relative to base_dir (workflow file's directory)
      2. Relative to project repo log-templates/ (walked up from base_dir)
      3. Relative to ~/.cline/skills/template-library/templates/ (deployed)
      4. Relative to <repo>/skills/template-library/templates/ (dev)

    If errors list is provided, warnings/errors are appended to it in addition
    to being printed to stderr.
    """
    if os.path.isabs(path):
        candidates = [path]
    else:
        candidates = [os.path.join(base_dir or os.getcwd(), path)]
        candidates += [os.path.join(d, path) for d in _project_template_dirs(base_dir or os.getcwd())]
        candidates += [os.path.join(d, path) for d in _SKILL_TEMPLATE_DIRS]

    resolved = next((os.path.normpath(p) for p in candidates if os.path.isfile(p)), None)
    if resolved is None:
        msg = f"Template '{path}' not found, skipping."
        print(f"  [WARN] {msg}", file=sys.stderr)
        if errors is not None:
            errors.append(f"[WARN] {msg}")
        return []
    try:
        data = yaml_utils.load_yaml(resolved) or {}
    except Exception as exc:
        msg = f"Failed to parse template YAML '{resolved}': {exc}"
        print(f"  [ERROR] {msg}", file=sys.stderr)
        if errors is not None:
            errors.append(f"[ERROR] {msg}")
        return []
    return data.get("templates", [])


def resolve_patterns(input_entry: dict, base_dir: str = "", errors: list = None) -> list:
    """
    Merge template entries from `include:` paths + inline `templates:` list.
    Inline entries win on id clash. Relative paths resolve against base_dir.
    If errors list is provided, template load warnings are appended to it.
    """
    merged = {}
    for template_path in (input_entry.get("include") or []):
        for p in load_template(template_path, base_dir, errors=errors):
            merged[p["id"]] = p
    for p in (input_entry.get("templates") or []):
        merged[p["id"]] = p
    return list(merged.values())


# ── Core runner ───────────────────────────────────────────────────────────────

def run_patterns(
    input_file: str,
    patterns: list,
    skill: str,
    max_lines: int = 200,
    script_dirs: Optional[list] = None,
) -> list:
    """
    Apply a list of resolved pattern dicts to input_file using the given skill.

    Args:
        input_file:   Path to the log or pcap file.
        patterns:     List of pattern dicts (already resolved via resolve_patterns).
        skill:        "android-log-analysis" or "android-pcap-analysis".
        max_lines:    Default cap (overridden per-pattern if pattern has max_lines).
        script_dirs:  Search dirs for post_process scripts.

    Returns:
        List of section dicts with keys:
            source_file, pattern_id, match_count, capped,
            description, filtered_lines, summary_prompt, error
    """
    script_dirs = script_dirs or []
    is_pcap = skill == "android-pcap-analysis"

    log_filter = load_skill_module("android-log-analysis", "log_filter")
    pcap_filter = load_skill_module("android-pcap-analysis", "pcap_filter")

    sections = []
    for pattern in patterns:
        pid = pattern.get("id", "unknown")
        desc = pattern.get("description", "")
        summary_prompt = pattern.get("summary_prompt")
        post_process = pattern.get("post_process")
        entry_max = pattern.get("max_lines", max_lines)

        print(f"    Pattern: {pid}", file=sys.stderr)

        if is_pcap:
            result = pcap_filter.filter_pcap(
                filepath=input_file,
                display_filter=pattern.get("filter", ""),
                fields=pattern.get("fields", []),
                pattern_id=pid,
                max_lines=entry_max,
                post_process=post_process,
                post_process_search_dirs=script_dirs,
            )
        else:
            result = log_filter.filter_file(
                filepath=input_file,
                pattern=pattern.get("pattern", ""),
                pattern_id=pid,
                context_lines=pattern.get("context_lines", 5),
                max_lines=entry_max,
                post_process=post_process,
                post_process_search_dirs=script_dirs,
            )

        sections.append({
            "source_file": os.path.basename(input_file),
            "pattern_id": pid,
            "match_count": result.match_count,
            "capped": result.capped,
            "description": desc,
            "filtered_lines": result.lines,
            "summary_prompt": summary_prompt,
            "error": result.error,
        })

    return sections


def run_template(
    template_path: str,
    input_file: str,
    skill: str = None,
    max_lines: int = 200,
    base_dir: str = "",
    script_dirs: Optional[list] = None,
) -> list:
    """
    Load a template YAML and apply it to input_file.

    Auto-detects skill (log vs pcap) from pattern structure if skill is None.
    Returns list of section dicts (same shape as run_patterns).
    """
    patterns = load_template(template_path, base_dir)
    if not patterns:
        return []

    if not skill:
        skill = "android-pcap-analysis" if any(
            "filter" in p and "fields" in p for p in patterns
        ) else "android-log-analysis"

    return run_patterns(
        input_file=input_file,
        patterns=patterns,
        skill=skill,
        max_lines=max_lines,
        script_dirs=script_dirs,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Apply a template YAML to a log or pcap file"
    )
    parser.add_argument("--template", required=True, help="Path to template YAML file")
    parser.add_argument("--file", required=True, help="Path to log or pcap file")
    parser.add_argument(
        "--skill",
        default=None,
        help="Skill to use: android-log-analysis or android-pcap-analysis (auto-detected if omitted)",
    )
    parser.add_argument("--max-lines", type=int, default=200, help="Max lines per pattern (default: 200)")
    args = parser.parse_args()

    template_path = os.path.abspath(args.template)
    input_file = os.path.abspath(args.file)
    base_dir = os.path.dirname(template_path)

    print(f"  Template:  {template_path}", file=sys.stderr)
    print(f"  Input:     {input_file}", file=sys.stderr)

    sections = run_template(
        template_path=template_path,
        input_file=input_file,
        skill=args.skill,
        max_lines=args.max_lines,
        base_dir=base_dir,
    )

    if not sections:
        print("No templates found or no matches.", file=sys.stderr)
        sys.exit(0)

    for section in sections:
        print(f"\n{'='*60}")
        print(f"# Pattern: {section['pattern_id']}  |  Source: {section['source_file']}  |  Matches: {section['match_count']}{' (capped)' if section['capped'] else ''}")
        if section.get("description"):
            print(f"# {section['description'].strip()}")
        print(f"{'='*60}")
        if section.get("error"):
            print(f"[ERROR] {section['error']}")
        elif section["filtered_lines"]:
            print(section["filtered_lines"])
        else:
            print("(no matches)")
