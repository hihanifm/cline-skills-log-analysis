"""
log_synthesizer_agent.py — LLM synthesis for log analysis context.

Reads log-context.md produced by context_builder_agent.py, generates
per-pattern summaries and a final summary using either an OpenAI-compatible
API or placeholder markers (for Cline to fill).

LLM backend is controlled by workflow_config.yaml (llm.backend) or the
LLM_BACKEND environment variable. API key is read from the LLM_API_KEY
environment variable.

Output is always written to:
    out/<workflow-name>/report.md

Usage:
    python3 log_synthesizer_agent.py \
        --context /path/to/out/<workflow-name>/log-context.md

Prints report path to stdout. Progress goes to stderr.
"""

import argparse
import os
import sys
from datetime import datetime


# Add shared modules dir to sys.path.
# In deployed mode setup.py copies shared modules alongside this script.
# In dev mode they live in lib/ under the repo root.
def _find_shared_modules_dir():
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        if os.path.isfile(os.path.join(d, "yaml_utils.py")):          # deployed
            return d
        if os.path.isfile(os.path.join(d, "lib", "yaml_utils.py")):   # dev/repo
            return os.path.join(d, "lib")
        parent = os.path.dirname(d)
        if parent == d:
            raise ImportError("Cannot find yaml_utils.py. Run setup.py to install.")
        d = parent

_SHARED = _find_shared_modules_dir()
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import yaml_utils
from config import get_llm_config, get_output_config


# ── Context reader ────────────────────────────────────────────────────────────

def load_context_yaml(path: str) -> dict:
    """Read log-context.md produced by context_builder_agent.py."""
    data = yaml_utils.load_yaml(path) or {}
    data.setdefault("sections", [])
    return data


# ── LLM API caller ────────────────────────────────────────────────────────────

def call_llm(api_key: str, prompt: str, context: str, base_url: str, model: str, max_tokens: int = 1024) -> str:
    """Call an OpenAI-compatible Chat Completions API. Returns generated text."""
    import json
    import urllib.request
    import urllib.error

    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": f"{prompt}\n\n<log_context>\n{context}\n</log_context>"
            }
        ]
    }

    url = base_url.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API error {e.code}: {body}")


# ── Report writer ─────────────────────────────────────────────────────────────

def write_report(context: dict, output_path: str):
    llm_cfg = get_llm_config()
    default_backend = str(llm_cfg.get("backend", "cline")).lower()
    base_url = str(llm_cfg.get("base_url", "https://api.openai.com/v1"))
    model = str(llm_cfg.get("model", "gpt-4o-mini"))

    backend = os.environ.get("LLM_BACKEND", default_backend).lower()
    api_key = os.environ.get("LLM_API_KEY", "")

    if backend == "openai" and not api_key:
        print("  [WARN] LLM_BACKEND=openai but LLM_API_KEY not set. "
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
                if backend == "openai":
                    print(f"    Summarizing pattern: {pid}", file=sys.stderr)
                    try:
                        summary = call_llm(api_key, summary_prompt, filtered, base_url, model)
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

        if backend == "openai":
            print("  Generating final summary...", file=sys.stderr)
            # Build a condensed context of all summaries for the final call
            all_context = "\n".join(
                f"Pattern {s['pattern_id']} ({s['match_count']} matches): "
                + (s.get("filtered_lines", "")[:500] or "[no matches]")
                for s in context.get("sections", [])
            )
            try:
                final_summary = call_llm(api_key, final_prompt, all_context, base_url, model, max_tokens=2048)
                lines.append(final_summary.strip())
                lines.append("")
            except RuntimeError as e:
                print(f"  [WARN] Final summary API call failed: {e}", file=sys.stderr)
                lines.append(_cline_placeholder("final", final_prompt))
        else:
            lines.append(_cline_placeholder("final", final_prompt))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Optionally render report.html alongside report.md
    if get_output_config().get("html_report", True):
        _scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        import report_html_renderer
        html_path = report_html_renderer.render(output_path)
        print(f"  HTML report: {html_path}", file=sys.stderr)

    # Optionally render report_interactive.html (no LLM needed — any backend)
    if get_output_config().get("interactive_html", True):
        _scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if _scripts_dir not in sys.path:
            sys.path.insert(0, _scripts_dir)
        import interactive_html_generator
        try:
            ihtml_path = interactive_html_generator.render(output_path)
            print(f"  Interactive HTML: {ihtml_path}", file=sys.stderr)
        except Exception as e:
            print(f"  [WARN] Interactive HTML generation failed: {e}", file=sys.stderr)

    # Write summary.md — final summary only (openai mode only;
    # in cline mode Cline fills the placeholder and writes summary.md itself)
    if backend == "openai" and final_prompt:
        summary_path = os.path.join(os.path.dirname(output_path), "summary.md")
        summary_lines = [
            f"# {workflow} — Summary",
            f"",
            f"**Input:** `{input_file}`",
            f"**Generated:** {ts}",
            f"",
        ]
        try:
            idx = lines.index("## FINAL SUMMARY")
            summary_lines += lines[idx + 2:]
        except ValueError:
            summary_lines.append("*(No final summary generated)*")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_lines) + "\n")


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
    parser.add_argument("--context", required=True, help="Path to log-context.md from context_builder_agent.py")
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
