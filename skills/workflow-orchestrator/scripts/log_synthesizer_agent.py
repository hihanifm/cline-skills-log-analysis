"""
log_synthesizer_agent.py — LLM synthesis for log analysis context.

Reads context.txt produced by context_builder_agent.py, generates
per-pattern summaries and a final summary using either the Anthropic
API or placeholder markers (for Cline to fill).

LLM backend is controlled by workflow_config.yaml (llm.backend) or the
LLM_BACKEND environment variable. API key is read from the environment
variable named by llm.api_key_env (default: ANTHROPIC_API_KEY).

Output is always written to:
    out/<workflow-name>/report.md

Usage:
    python3 log_synthesizer_agent.py \
        --context /path/to/out/<workflow-name>/context.txt

Prints report path to stdout. Progress goes to stderr.
"""

import argparse
import os
import sys
from datetime import datetime


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
from config import get_llm_config


# ── Context reader ────────────────────────────────────────────────────────────

def load_context_yaml(path: str) -> dict:
    """Read context.txt produced by context_builder_agent.py."""
    data = yaml_utils.load_yaml(path) or {}
    data.setdefault("sections", [])
    return data


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

def write_report(context: dict, output_path: str):
    llm_cfg = get_llm_config()
    default_backend = str(llm_cfg.get("backend", "cline")).lower()
    api_key_env = llm_cfg.get("api_key_env", "ANTHROPIC_API_KEY")

    backend = os.environ.get("LLM_BACKEND", default_backend).lower()
    api_key = os.environ.get(api_key_env, "")

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
    parser.add_argument("--context", required=True, help="Path to context.txt from context_builder_agent.py")
    args = parser.parse_args()

    context_path = os.path.abspath(args.context)
    context_dir = os.path.dirname(context_path)
    output_path = os.path.join(context_dir, "report.md")

    print(f"  Context:   {context_path}", file=sys.stderr)
    print(f"  Report:    {output_path}", file=sys.stderr)

    context = load_context_yaml(context_path)
    write_report(context, output_path)

    total = len(context.get("sections", []))
    matched = sum(1 for s in context.get("sections", []) if s.get("match_count", 0) > 0)
    print(f"  Done: {matched}/{total} patterns had matches.", file=sys.stderr)

    # Print report path to stdout for Cline to capture
    print(output_path)


if __name__ == "__main__":
    main()
