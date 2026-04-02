"""
context_builder_agent.py — Deterministic log context builder.

Reads a workflow .md YAML frontmatter, resolves input files (file/folder/zip),
delegates filtering to the template-engine skill, and writes a structured
context file for log_synthesizer_agent.py to process.

Output is always written to:
    out/<workflow-name>/context.txt

Usage:
    python3 context_builder_agent.py \
        --workflow /path/to/battery-troubleshooting.md \
        --input /path/to/logcat.txt

Prints context file path to stdout. Progress goes to stderr.
"""

import argparse
import fnmatch
import importlib.util
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional


# Add shared modules dir to sys.path.
# In dev mode this is the repo root (contains yaml_utils.py).
# In deployed mode setup.py copies shared modules alongside this script.
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


# ── Project dir helper ───────────────────────────────────────────────────────

def _find_project_dir(base_dir: str, subdir: str) -> str:
    """
    Walk up from base_dir looking for a <subdir>/ directory in the project repo.
    Returns the path if found, otherwise returns a non-existent path that will
    simply be skipped by the script search logic.
    """
    d = base_dir
    for _ in range(4):
        candidate = os.path.join(d, subdir)
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.join(base_dir, subdir)  # non-existent, harmlessly skipped


# ── Skill module loader ───────────────────────────────────────────────────────

def _load_skill_module(skill_name: str, module_name: str):
    """
    Dynamically import a skill module from ~/.cline/skills/<skill_name>/scripts/<module_name>.py
    """
    skill_dir = os.path.join(os.path.expanduser("~"), ".cline", "skills", skill_name, "scripts")
    module_path = os.path.join(skill_dir, f"{module_name}.py")

    if not os.path.isfile(module_path):
        # Fallback: look relative to shared modules dir (dev mode, _SHARED == repo root)
        module_path = os.path.join(_SHARED, "skills", skill_name, "scripts", f"{module_name}.py")

    if not os.path.isfile(module_path):
        raise ImportError(f"Cannot find {module_name}.py for skill '{skill_name}'. "
                          f"Run setup.py to install skills first.")

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Input file resolver ───────────────────────────────────────────────────────

def _resolve_input_files(input_path: str, glob_pattern: str) -> list:
    """
    Given an input path (file/folder/zip) and a glob pattern,
    return list of absolute file paths to process.
    """
    if os.path.isfile(input_path):
        ext = os.path.splitext(input_path)[1].lower()
        if ext == ".zip":
            return _extract_from_zip(input_path, glob_pattern)
        # For a regular single file input, ignore the workflow glob pattern
        # and process the file as-is without validation.
        return [input_path]

    elif os.path.isdir(input_path):
        matches = []
        for fname in os.listdir(input_path):
            if fnmatch.fnmatch(fname, glob_pattern):
                matches.append(os.path.join(input_path, fname))
        return sorted(matches)

    else:
        print(f"  [ERROR] Input path not found: {input_path}", file=sys.stderr)
        return []


def _extract_from_zip(zip_path: str, glob_pattern: str) -> list:
    """Extract matching files from zip to <zip_dir>/<zip_name>_extracted/. Returns paths."""
    zip_dir = os.path.dirname(zip_path)
    zip_name = os.path.splitext(os.path.basename(zip_path))[0]
    extract_dir = os.path.join(zip_dir, f"{zip_name}_extracted")

    with zipfile.ZipFile(zip_path, "r") as zf:
        all_names = zf.namelist()
        matched = [n for n in all_names if fnmatch.fnmatch(os.path.basename(n), glob_pattern)]

        if not matched:
            print(f"  [WARN] No files matching '{glob_pattern}' in {zip_path}", file=sys.stderr)
            return []

        extracted = []
        for name in matched:
            dest = os.path.join(extract_dir, os.path.basename(name))
            if not os.path.isfile(dest):
                os.makedirs(extract_dir, exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as dst:
                    dst.write(src.read())
                print(f"  Extracted: {name} → {dest}", file=sys.stderr)
            else:
                print(f"  Cached:    {dest}", file=sys.stderr)
            extracted.append(dest)

    return extracted


# ── Context YAML writer ───────────────────────────────────────────────────────

def _yaml_str(val, indent=0) -> str:
    """Simple YAML serializer for context output."""
    pad = "  " * indent
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, list):
        if not val:
            return "[]"
        lines = [f"{pad}- {_yaml_str(item, indent + 1)}" for item in val]
        return "\n" + "\n".join(lines)
    if isinstance(val, dict):
        lines = []
        for k, v in val.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines.append(_indent_block(_yaml_str(v, indent + 1), pad + "  "))
            elif isinstance(v, str) and "\n" in v:
                lines.append(f"{pad}{k}: |")
                for subline in v.splitlines():
                    lines.append(f"{pad}  {subline}")
            else:
                lines.append(f"{pad}{k}: {_yaml_str(v, indent)}")
        return "\n".join(lines)
    if isinstance(val, str):
        if "\n" in val or '"' in val or ":" in val or val.startswith("#"):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return val
    return str(val)


def _indent_block(text: str, pad: str) -> str:
    return "\n".join(f"{pad}{line}" if line.strip() else line for line in text.splitlines())


def _write_context_yaml(path: str, data: dict):
    """Write context dict to a YAML file."""
    lines = [
        f"workflow: {data['workflow']}",
        f"input_file: {data['input_file']}",
        f"timestamp: {data['timestamp']}",
        "sections:",
    ]

    for s in data["sections"]:
        lines.append(f"  - input_glob: \"{s['input_glob']}\"")
        lines.append(f"    source_file: \"{s['source_file']}\"")
        lines.append(f"    pattern_id: {s['pattern_id']}")
        lines.append(f"    match_count: {s['match_count']}")
        lines.append(f"    capped: {'true' if s['capped'] else 'false'}")
        # Description — escape quotes
        desc = s.get('description', '').replace('"', '\\"')
        lines.append(f"    description: \"{desc}\"")
        if s.get("error"):
            lines.append(f"    error: \"{s['error']}\"")
        # filtered_lines as literal block
        fl = s.get("filtered_lines", "")
        if fl:
            lines.append("    filtered_lines: |")
            for fl_line in fl.splitlines():
                lines.append(f"      {fl_line}")
        else:
            lines.append("    filtered_lines: \"\"")
        # summary_prompt
        sp = s.get("summary_prompt")
        if sp:
            lines.append(f"    summary_prompt: \"{sp.strip().replace(chr(10), ' ')}\"")
        else:
            lines.append("    summary_prompt: null")
        lines.append("    summary: null")
        lines.append("")

    # Final summary
    fsp = data.get("final_summary_prompt")
    if fsp:
        lines.append(f"final_summary_prompt: \"{fsp.strip().replace(chr(10), ' ')}\"")
    else:
        lines.append("final_summary_prompt: null")
    lines.append("final_summary: null")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build log analysis context from a workflow.")
    parser.add_argument("--workflow", required=True, help="Path to workflow .md file")
    parser.add_argument("--input", required=True, help="Input log file, folder, or zip archive")
    parser.add_argument("--max-lines", type=int, default=None, help="Override default max lines cap")
    args = parser.parse_args()

    workflow_path = os.path.abspath(args.workflow)
    input_path = os.path.abspath(args.input)
    workflow_dir = os.path.dirname(workflow_path)

    print(f"  Workflow:  {workflow_path}", file=sys.stderr)
    print(f"  Input:     {input_path}", file=sys.stderr)

    # Parse workflow frontmatter
    config = yaml_utils.load_yaml_frontmatter(workflow_path)
    workflow_name = config.get("workflow", os.path.splitext(os.path.basename(workflow_path))[0])
    default_max = args.max_lines or config.get("default_max_lines", 200)

    # Output goes to out/<workflow-name>/ or out/<workflow-name>-2/, -3/, etc.
    # if the directory already exists (preserves previous runs).
    base_dir = Path("out") / workflow_name
    out_dir = base_dir
    if out_dir.exists():
        n = 2
        while True:
            candidate = Path("out") / f"{workflow_name}-{n}"
            if not candidate.exists():
                out_dir = candidate
                break
            n += 1
    out_dir.mkdir(parents=True, exist_ok=True)
    context_path = str(out_dir / "context.txt")

    # Load template engine
    template_runner = _load_skill_module("template-engine", "template_runner")

    # Process input entries
    sections = []
    errors = []
    for input_entry in (config.get("input") or []):
        glob_pattern = input_entry.get("path", "*")
        matched_files = _resolve_input_files(input_path, glob_pattern)

        if not matched_files:
            msg = f"No files matched glob '{glob_pattern}'"
            print(f"  [WARN] {msg}", file=sys.stderr)
            errors.append(f"[WARN] {msg}")
            sections.append({
                "input_glob": glob_pattern,
                "source_file": "",
                "pattern_id": "_no_match",
                "match_count": 0,
                "capped": False,
                "description": f"No files matched pattern: {glob_pattern}",
                "filtered_lines": "",
                "summary_prompt": None,
            })
            continue

        # Resolve skill and patterns via template_runner
        skill_name = input_entry.get("skill")
        all_patterns = template_runner.resolve_patterns(input_entry, workflow_dir, errors=errors)
        if not all_patterns:
            msg = f"No patterns resolved for glob '{glob_pattern}' — check include paths and template IDs."
            print(f"  [WARN] {msg}", file=sys.stderr)
            errors.append(f"[WARN] {msg}")
        if not skill_name:
            skill_name = "android-pcap-analysis" if any(
                "filter" in p and "fields" in p for p in all_patterns
            ) else "android-log-analysis"

        # Script search dirs for post_process resolution.
        # Project postprocessors/ is found by walking up from workflow_dir.
        skill_scripts_dir = os.path.join(
            os.path.expanduser("~"), ".cline", "skills", skill_name, "scripts"
        )
        workflow_scripts_dir = os.path.join(workflow_dir, "scripts")
        postprocessors_dir = os.path.join(
            os.path.expanduser("~"), ".cline", "skills", "postprocessors", "scripts"
        )
        postprocessors_dir_dev = os.path.join(_SHARED, "skills", "postprocessors", "scripts")
        project_postprocessors_dir = _find_project_dir(workflow_dir, "log-postprocessors")
        script_dirs = [
            workflow_scripts_dir,
            project_postprocessors_dir,
            postprocessors_dir,
            postprocessors_dir_dev,
            skill_scripts_dir,
        ]

        for src_file in matched_files:
            print(f"  Processing: {os.path.basename(src_file)}", file=sys.stderr)
            entry_sections = template_runner.run_patterns(
                input_file=src_file,
                patterns=all_patterns,
                skill=skill_name,
                max_lines=default_max,
                script_dirs=script_dirs,
            )
            for s in entry_sections:
                s["input_glob"] = glob_pattern
            sections.extend(entry_sections)

    # Write context YAML
    context_data = {
        "workflow": workflow_name,
        "input_file": input_path,
        "timestamp": datetime.now().isoformat(),
        "default_max_lines": default_max,
        "sections": sections,
        "final_summary_prompt": config.get("final_summary_prompt"),
    }

    _write_context_yaml(context_path, context_data)

    # Collect per-pattern errors from sections
    for s in sections:
        if s.get("error"):
            errors.append(f"[ERROR] pattern '{s['pattern_id']}' in '{s['source_file']}': {s['error']}")

    # Write errors.txt if any errors/warnings were collected
    if errors:
        errors_path = str(out_dir / "errors.txt")
        with open(errors_path, "w", encoding="utf-8") as f:
            f.write(f"Run: {datetime.now().isoformat()}\n")
            f.write(f"Workflow: {workflow_path}\n")
            f.write(f"Input: {input_path}\n")
            f.write("\n")
            for e in errors:
                f.write(e + "\n")
        print(f"  Errors:    {errors_path}", file=sys.stderr)

    total_matches = sum(s["match_count"] for s in sections)
    matched_patterns = sum(1 for s in sections if s["match_count"] > 0)
    print(f"  Done: {matched_patterns}/{len(sections)} patterns matched, "
          f"{total_matches} total matches", file=sys.stderr)

    # Print context file path to stdout (for Cline to capture)
    print(context_path)


if __name__ == "__main__":
    main()
