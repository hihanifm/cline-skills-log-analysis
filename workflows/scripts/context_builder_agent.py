"""
context_builder_agent.py — Deterministic log context builder.

Reads a workflow .md YAML frontmatter, resolves input files (file/folder/zip),
imports log_filter / pcap_filter skill modules, runs all patterns, and writes
a structured context.yaml file for log_synthesizer_agent.py to process.

Usage:
    python3 context_builder_agent.py \
        --workflow /path/to/battery-troubleshooting.md \
        --input /path/to/logcat.txt \
        [--output-dir ./output]

Prints context YAML file path to stdout. Progress goes to stderr.
"""

import argparse
import fnmatch
import importlib.util
import os
import re
import sys
import zipfile
from datetime import datetime
from typing import Optional


# ── YAML frontmatter parser (stdlib only) ────────────────────────────────────

def parse_frontmatter(md_path: str) -> dict:
    """
    Extract and parse YAML frontmatter from a .md file.
    Uses a minimal recursive parser — no PyYAML needed.
    """
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        raise ValueError(f"No YAML frontmatter found in {md_path}")

    return _parse_yaml_block(m.group(1))


def _parse_yaml_block(text: str) -> dict:
    """Minimal YAML parser supporting str, int, list, nested dict, multiline >."""
    lines = text.splitlines()
    result, i = {}, 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.strip().startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        stripped = line.strip()

        if stripped.startswith("- "):
            # Top-level list item — shouldn't happen at root, skip
            i += 1
            continue

        if ":" in stripped:
            key, _, rest = stripped.partition(":")
            key = key.strip()
            rest = rest.strip()

            if rest == ">":
                # Multiline folded scalar
                val_lines, i = [], i + 1
                base_indent = None
                while i < len(lines):
                    vl = lines[i]
                    if not vl.strip():
                        val_lines.append("")
                        i += 1
                        continue
                    vi = len(vl) - len(vl.lstrip())
                    if base_indent is None:
                        base_indent = vi
                    if vi < (base_indent or 0):
                        break
                    val_lines.append(vl.strip())
                    i += 1
                result[key] = " ".join(v for v in val_lines if v)
                continue

            elif rest == "":
                # Nested block — collect indented lines
                nested_lines, i = [], i + 1
                while i < len(lines):
                    nl = lines[i]
                    if not nl.strip():
                        i += 1
                        continue
                    ni = len(nl) - len(nl.lstrip())
                    if ni <= indent:
                        break
                    nested_lines.append(nl[indent + 2:] if len(nl) > indent + 2 else nl.lstrip())
                    i += 1

                # Detect if it's a list or dict
                if nested_lines and nested_lines[0].startswith("- "):
                    result[key] = _parse_yaml_list(nested_lines)
                else:
                    result[key] = _parse_yaml_block("\n".join(nested_lines))
                continue

            else:
                result[key] = _parse_scalar(rest)

        i += 1

    return result


def _parse_yaml_list(lines: list) -> list:
    """Parse a YAML list block into a list of dicts or scalars."""
    items, current_item_lines = [], []

    for line in lines:
        if line.startswith("- "):
            if current_item_lines:
                items.append(_parse_yaml_block("\n".join(current_item_lines)))
                current_item_lines = []
            rest = line[2:].strip()
            if rest:
                current_item_lines.append(rest)
        else:
            current_item_lines.append(line)

    if current_item_lines:
        items.append(_parse_yaml_block("\n".join(current_item_lines)))

    return items


def _parse_scalar(val: str):
    """Parse a scalar value: int, bool, quoted string, bracket list, or plain string."""
    val = val.strip()
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1]
        return [v.strip().strip('"\'') for v in inner.split(",") if v.strip()]
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.lower() in ("null", "~", ""):
        return None
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


# ── Skill module loader ───────────────────────────────────────────────────────

def _load_skill_module(skill_name: str, module_name: str):
    """
    Dynamically import a skill module from ~/.cline/skills/<skill_name>/scripts/<module_name>.py
    """
    skill_dir = os.path.join(os.path.expanduser("~"), ".cline", "skills", skill_name, "scripts")
    module_path = os.path.join(skill_dir, f"{module_name}.py")

    if not os.path.isfile(module_path):
        # Fallback: look relative to this script (dev mode)
        here = os.path.dirname(os.path.abspath(__file__))
        repo_root = os.path.dirname(os.path.dirname(here))
        module_path = os.path.join(repo_root, "skills", skill_name, "scripts", f"{module_name}.py")

    if not os.path.isfile(module_path):
        raise ImportError(f"Cannot find {module_name}.py for skill '{skill_name}'. "
                          f"Run setup.py to install skills first.")

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Pattern template loader ───────────────────────────────────────────────────

def _load_template_file(path: str, workflow_dir: str) -> list:
    """Load a template YAML by path. Relative paths resolve against workflow_dir."""
    if not os.path.isabs(path):
        path = os.path.join(workflow_dir, path)
    path = os.path.normpath(path)
    if not os.path.isfile(path):
        print(f"  [WARN] Template '{path}' not found, skipping.", file=sys.stderr)
        return []
    with open(path, encoding="utf-8") as f:
        data = _parse_yaml_block(f.read())
    return data.get("templates", [])


def _resolve_patterns(input_entry: dict, skill_name: str, workflow_dir: str = "") -> list:
    """Merge included templates + inline definitions. Inline wins on id clash."""
    merged = {}

    for template_path in (input_entry.get("include") or []):
        for p in _load_template_file(template_path, workflow_dir):
            merged[p["id"]] = p

    for p in (input_entry.get("templates") or []):
        merged[p["id"]] = p  # inline overrides

    return list(merged.values())


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
        else:
            # Single file — check if it matches glob (warn if not, still use it)
            if not fnmatch.fnmatch(os.path.basename(input_path), glob_pattern):
                print(f"  [WARN] File '{os.path.basename(input_path)}' does not match "
                      f"glob '{glob_pattern}', processing anyway.", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="Build log analysis context YAML from a workflow.")
    parser.add_argument("--workflow", required=True, help="Path to workflow .md file")
    parser.add_argument("--input", required=True, help="Input log file, folder, or zip archive")
    parser.add_argument("--output-dir", default=None, help="Override output directory")
    parser.add_argument("--max-lines", type=int, default=None, help="Override default max lines cap")
    args = parser.parse_args()

    workflow_path = os.path.abspath(args.workflow)
    input_path = os.path.abspath(args.input)
    workflow_dir = os.path.dirname(workflow_path)

    print(f"  Workflow:  {workflow_path}", file=sys.stderr)
    print(f"  Input:     {input_path}", file=sys.stderr)

    # Parse workflow frontmatter
    config = parse_frontmatter(workflow_path)
    workflow_name = config.get("workflow", os.path.splitext(os.path.basename(workflow_path))[0])
    default_max = args.max_lines or config.get("default_max_lines", 200)

    # Resolve output dir
    output_cfg = config.get("output", {})
    out_dir = args.output_dir or output_cfg.get("dir", "./output")
    if not os.path.isabs(out_dir):
        out_dir = os.path.join(os.path.dirname(input_path), out_dir)
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_filename = output_cfg.get("filename", "context_{{timestamp}}.yaml")
    out_filename = out_filename.replace("{{timestamp}}", ts)
    # Force .yaml extension for context file
    out_filename = re.sub(r"\.(txt|md)$", ".yaml", out_filename)
    if not out_filename.endswith(".yaml"):
        out_filename = os.path.splitext(out_filename)[0] + f"_context_{ts}.yaml"
    context_path = os.path.join(out_dir, out_filename)

    # Load skill modules
    log_filter = _load_skill_module("android-log-analysis", "log_filter")
    pcap_filter = _load_skill_module("android-pcap-analysis", "pcap_filter")

    # Check deps
    try:
        log_filter.check_dependencies()
    except log_filter.ToolNotFoundError as e:
        print(f"  [ERROR] {e}", file=sys.stderr)
        # Don't exit — log patterns will fail gracefully, pcap may still work

    try:
        pcap_filter.check_dependencies()
    except pcap_filter.ToolNotFoundError as e:
        print(f"  [WARN] {e}", file=sys.stderr)

    # Process input entries
    sections = []
    for input_entry in (config.get("input") or []):
        glob_pattern = input_entry.get("path", "*")
        matched_files = _resolve_input_files(input_path, glob_pattern)

        if not matched_files:
            print(f"  [WARN] No files matched glob '{glob_pattern}'", file=sys.stderr)
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

        # Select skill from explicit declaration; fall back to pattern-structure heuristic
        skill_name = input_entry.get("skill")
        if not skill_name:
            all_patterns = _resolve_patterns(input_entry, "android-log-analysis", workflow_dir)
            skill_name = "android-pcap-analysis" if any(
                "filter" in p and "fields" in p for p in all_patterns
            ) else "android-log-analysis"
        is_pcap = skill_name == "android-pcap-analysis"
        all_patterns = _resolve_patterns(input_entry, skill_name, workflow_dir)

        # Script search dirs for post_process resolution
        skill_scripts_dir = os.path.join(
            os.path.expanduser("~"), ".cline", "skills", skill_name, "scripts"
        )
        workflow_scripts_dir = os.path.join(workflow_dir, "scripts")
        script_dirs = [workflow_scripts_dir, skill_scripts_dir]

        for src_file in matched_files:
            print(f"  Processing: {os.path.basename(src_file)}", file=sys.stderr)

            for pattern in all_patterns:
                pid = pattern.get("id", "unknown")
                desc = pattern.get("description", "")
                summary_prompt = pattern.get("summary_prompt")
                post_process = pattern.get("post_process")
                max_lines = pattern.get("max_lines", default_max)

                print(f"    Pattern: {pid}", file=sys.stderr)

                if is_pcap:
                    result = pcap_filter.filter_pcap(
                        filepath=src_file,
                        display_filter=pattern.get("filter", ""),
                        fields=pattern.get("fields", []),
                        pattern_id=pid,
                        max_lines=max_lines,
                        post_process=post_process,
                        post_process_search_dirs=script_dirs,
                    )
                else:
                    result = log_filter.filter_file(
                        filepath=src_file,
                        pattern=pattern.get("pattern", ""),
                        pattern_id=pid,
                        context_lines=pattern.get("context_lines", 5),
                        max_lines=max_lines,
                        post_process=post_process,
                        post_process_search_dirs=script_dirs,
                    )

                sections.append({
                    "input_glob": glob_pattern,
                    "source_file": os.path.basename(src_file),
                    "pattern_id": pid,
                    "match_count": result.match_count,
                    "capped": result.capped,
                    "description": desc,
                    "filtered_lines": result.lines,
                    "summary_prompt": summary_prompt,
                    "error": result.error,
                })

    # Write context YAML
    context_data = {
        "workflow": workflow_name,
        "input_file": input_path,
        "timestamp": datetime.now().isoformat(),
        "sections": sections,
        "final_summary_prompt": config.get("final_summary_prompt"),
    }

    _write_context_yaml(context_path, context_data)

    total_matches = sum(s["match_count"] for s in sections)
    matched_patterns = sum(1 for s in sections if s["match_count"] > 0)
    print(f"  Done: {matched_patterns}/{len(sections)} patterns matched, "
          f"{total_matches} total matches", file=sys.stderr)

    # Print context file path to stdout (for Cline to capture)
    print(context_path)


if __name__ == "__main__":
    main()
