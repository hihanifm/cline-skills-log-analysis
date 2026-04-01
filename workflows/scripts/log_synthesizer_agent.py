"""
log_synthesizer_agent.py — LLM synthesis for log analysis context.

Reads context.yaml produced by context_builder_agent.py, generates
per-pattern summaries and a final summary using either the Anthropic
API or placeholder markers (for Cline to fill).

LLM backend is resolved from .env:
    LLM_BACKEND=anthropic   → calls Anthropic API directly
    LLM_BACKEND=cline       → writes <!-- SUMMARY_PROMPT --> markers for Cline

Usage:
    python3 log_synthesizer_agent.py \
        --context /path/to/context.yaml \
        [--output /path/to/final_report.md] \
        [--env /path/to/.env]

Prints final report path to stdout. Progress goes to stderr.
"""

import argparse
import os
import re
import sys
from datetime import datetime


# ── .env loader ───────────────────────────────────────────────────────────────

def load_env(env_path: str) -> dict:
    """Load key=value pairs from a .env file. Returns dict."""
    env = {}
    if not os.path.isfile(env_path):
        return env
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def resolve_env(args_env: str = None) -> dict:
    """
    Search for .env file: args_env → workflow dir → project root → home.
    Merge with os.environ (os.environ takes precedence).
    """
    candidates = []
    if args_env:
        candidates.append(args_env)

    # Walk up from this script's location
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        candidates.append(os.path.join(here, ".env"))
        here = os.path.dirname(here)

    env = {}
    for c in candidates:
        if os.path.isfile(c):
            env = load_env(c)
            print(f"  Loaded .env from: {c}", file=sys.stderr)
            break

    # os.environ overrides .env
    for key in ("ANTHROPIC_API_KEY", "LLM_BACKEND"):
        if key in os.environ:
            env[key] = os.environ[key]

    return env


# ── Minimal context YAML reader ───────────────────────────────────────────────

def load_context_yaml(path: str) -> dict:
    """
    Read context.yaml. Uses a simple line-based parser for the known schema.
    Handles the literal block scalar (|) for filtered_lines.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    result = {"sections": []}
    current_section = None
    current_block_key = None
    current_block_indent = None
    current_block_lines = []
    i = 0

    def flush_block():
        nonlocal current_block_key, current_block_lines, current_block_indent
        if current_block_key and current_section is not None:
            current_section[current_block_key] = "\n".join(current_block_lines)
        elif current_block_key:
            result[current_block_key] = "\n".join(current_block_lines)
        current_block_key = None
        current_block_lines = []
        current_block_indent = None

    while i < len(lines):
        raw = lines[i].rstrip("\n")
        stripped = raw.strip()
        indent = len(raw) - len(raw.lstrip())

        # Inside a literal block scalar
        if current_block_key is not None:
            if not stripped:
                current_block_lines.append("")
                i += 1
                continue
            if current_block_indent is None:
                current_block_indent = indent
            if indent >= current_block_indent:
                current_block_lines.append(raw[current_block_indent:])
                i += 1
                continue
            else:
                flush_block()
                # Don't increment i — re-process this line
                continue

        if stripped.startswith("- input_glob:"):
            flush_block()
            if current_section is not None:
                result["sections"].append(current_section)
            val = _extract_val(stripped, "input_glob")
            current_section = {"input_glob": val}
            i += 1
            continue

        if stripped == "sections:":
            i += 1
            continue

        key, val = _split_kv(stripped)
        if key is None:
            i += 1
            continue

        if val == "|":
            # Start of literal block scalar
            current_block_key = key
            current_block_lines = []
            current_block_indent = None
            i += 1
            continue

        parsed_val = _parse_val(val)

        if current_section is not None and indent >= 4:
            current_section[key] = parsed_val
        else:
            result[key] = parsed_val

        i += 1

    flush_block()
    if current_section is not None:
        result["sections"].append(current_section)

    return result


def _split_kv(line: str):
    if ":" not in line:
        return None, None
    key, _, val = line.partition(":")
    return key.strip(), val.strip()


def _extract_val(line: str, key: str) -> str:
    m = re.search(rf'{key}:\s*"?(.*?)"?\s*$', line)
    return m.group(1) if m else ""


def _parse_val(val: str):
    if val in ("null", "~", ""):
        return None
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    if val.startswith('"') and val.endswith('"'):
        return val[1:-1]
    if val.startswith("'") and val.endswith("'"):
        return val[1:-1]
    try:
        return int(val)
    except ValueError:
        pass
    return val


# ── Anthropic API caller ──────────────────────────────────────────────────────

def call_anthropic(api_key: str, prompt: str, context: str, max_tokens: int = 1024) -> str:
    """Call Anthropic Messages API. Returns generated text."""
    import json
    import urllib.request
    import urllib.error

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\n<log_context>\n{context}\n</log_context>"
            }
        ]
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic API error {e.code}: {body}")


# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(context: dict, output_path: str, env: dict):
    backend = env.get("LLM_BACKEND", "cline").lower()
    api_key = env.get("ANTHROPIC_API_KEY", "")

    if backend == "anthropic" and not api_key:
        print("  [WARN] LLM_BACKEND=anthropic but ANTHROPIC_API_KEY not set. "
              "Falling back to cline mode.", file=sys.stderr)
        backend = "cline"

    print(f"  LLM backend: {backend}", file=sys.stderr)

    workflow = context.get("workflow", "unknown")
    input_file = context.get("input_file", "")
    ts = context.get("timestamp", datetime.now().isoformat())

    lines = [
        f"# {workflow} — Analysis Report",
        f"",
        f"**Input:** `{input_file}`",
        f"**Generated:** {ts}",
        f"",
    ]

    # Group sections by input_glob
    by_glob = {}
    for section in context.get("sections", []):
        glob = section.get("input_glob", "unknown")
        by_glob.setdefault(glob, []).append(section)

    for glob, sections in by_glob.items():
        lines.append(f"## INPUT: {glob}")
        lines.append("")

        for s in sections:
            pid = s.get("pattern_id", "")
            source = s.get("source_file", "")
            count = s.get("match_count", 0)
            capped = s.get("capped", False)
            desc = s.get("description", "")
            filtered = s.get("filtered_lines", "") or ""
            summary_prompt = s.get("summary_prompt")
            error = s.get("error")

            cap_note = f" (showing last {context.get('default_max_lines', 200)})" if capped else ""
            lines.append(f"---")
            lines.append(f"**PATTERN:** {pid}  |  **SOURCE:** {source}  |  **MATCHES:** {count}{cap_note}")
            lines.append(f"*{desc}*")
            lines.append("")

            if error:
                lines.append(f"> ⚠️ {error}")
                lines.append("")
            elif count == 0:
                lines.append("[No matches found]")
                lines.append("")
            else:
                lines.append("```")
                lines.append(filtered.rstrip())
                lines.append("```")
                lines.append("")

            # Summary
            if summary_prompt and count > 0:
                if backend == "anthropic":
                    print(f"    Summarizing pattern: {pid}", file=sys.stderr)
                    try:
                        summary = call_anthropic(api_key, summary_prompt, filtered)
                        lines.append(f"**SUMMARY:**")
                        lines.append(summary.strip())
                        lines.append("")
                    except RuntimeError as e:
                        print(f"    [WARN] API call failed: {e}", file=sys.stderr)
                        lines.append(_cline_placeholder(pid, summary_prompt))
                else:
                    lines.append(_cline_placeholder(pid, summary_prompt))

    # Final summary
    final_prompt = context.get("final_summary_prompt")
    if final_prompt:
        lines.append("---")
        lines.append("## FINAL SUMMARY")
        lines.append("")

        if backend == "anthropic":
            print("  Generating final summary...", file=sys.stderr)
            # Build a condensed context of all summaries for the final call
            all_context = "\n".join(
                f"Pattern {s['pattern_id']} ({s['match_count']} matches): "
                + (s.get("filtered_lines", "")[:500] or "[no matches]")
                for s in context.get("sections", [])
            )
            try:
                final_summary = call_anthropic(api_key, final_prompt, all_context, max_tokens=2048)
                lines.append(final_summary.strip())
                lines.append("")
            except RuntimeError as e:
                print(f"  [WARN] Final summary API call failed: {e}", file=sys.stderr)
                lines.append(_cline_placeholder("final", final_prompt))
        else:
            lines.append(_cline_placeholder("final", final_prompt))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _cline_placeholder(pattern_id: str, prompt: str) -> str:
    """Write a placeholder marker for Cline to fill in."""
    return (
        f"<!-- SUMMARY_PROMPT: {pattern_id}\n"
        f"{prompt.strip()}\n"
        f"-->"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Synthesize log analysis context into a report.")
    parser.add_argument("--context", required=True, help="Path to context.yaml from context_builder_agent.py")
    parser.add_argument("--output", default=None, help="Output report path (default: <context_dir>/report.md)")
    parser.add_argument("--env", default=None, help="Path to .env file")
    args = parser.parse_args()

    context_path = os.path.abspath(args.context)
    context_dir = os.path.dirname(context_path)

    if args.output:
        output_path = os.path.abspath(args.output)
    else:
        base = os.path.splitext(os.path.basename(context_path))[0]
        output_path = os.path.join(context_dir, base.replace("_context", "_report") + ".md")

    print(f"  Context:   {context_path}", file=sys.stderr)
    print(f"  Report:    {output_path}", file=sys.stderr)

    env = resolve_env(args.env)
    context = load_context_yaml(context_path)
    write_report(context, output_path, env)

    total = len(context.get("sections", []))
    matched = sum(1 for s in context.get("sections", []) if s.get("match_count", 0) > 0)
    print(f"  Done: {matched}/{total} patterns had matches.", file=sys.stderr)

    # Print report path to stdout for Cline to capture
    print(output_path)


if __name__ == "__main__":
    main()
