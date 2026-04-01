"""
pcap_filter.py — Importable skill module for PCAP filtering via tshark.

Exposes a clean Python API used by context_builder_agent.py.
Can also be run directly as a CLI tool.

Usage (library):
    import sys, os
    sys.path.insert(0, '<pcap_skill_dir>/scripts')
    from pcap_filter import filter_pcap, check_dependencies, ToolNotFoundError

Usage (CLI):
    python3 pcap_filter.py --file <pcap_file> --filter "<display_filter>" --fields frame.number frame.time ... [--max-lines N]
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, List


class ToolNotFoundError(Exception):
    """Raised when tshark is not installed."""
    pass


@dataclass
class FilterResult:
    pattern_id: str
    source_file: str
    match_count: int
    capped: bool
    lines: str
    error: Optional[str] = None


def check_dependencies():
    """
    Check that tshark is installed.
    Raises ToolNotFoundError with install instructions if missing.
    """
    if shutil.which("tshark") is None:
        raise ToolNotFoundError(
            "tshark is not installed or not in PATH.\n"
            "Install instructions:\n"
            "  macOS:          brew install wireshark\n"
            "  Linux (apt):    sudo apt install tshark\n"
            "  Linux (dnf):    sudo dnf install wireshark-cli\n"
            "  Windows:        winget install WiresharkFoundation.Wireshark\n"
            "                  (or https://www.wireshark.org/download.html)\n"
        )


def filter_pcap(
    filepath: str,
    display_filter: str,
    fields: List[str],
    pattern_id: str = "pattern",
    max_lines: int = 200,
    post_process: Optional[str] = None,
    post_process_search_dirs: Optional[list] = None,
) -> FilterResult:
    """
    Run tshark on filepath with a display filter, extracting specified fields.

    Args:
        filepath:                  Path to the .pcap or .pcapng file.
        display_filter:            tshark display filter (e.g. "sip.Method").
        fields:                    List of tshark field names to extract.
        pattern_id:                ID label for this pattern.
        max_lines:                 Max output lines to keep (simple tail cap).
        post_process:              Script filename to pipe output through (optional).
        post_process_search_dirs:  Directories to search for post_process script.

    Returns:
        FilterResult with filtered packet text and metadata.
    """
    source_name = os.path.basename(filepath)

    # Build tshark command
    tshark_cmd = ["tshark", "-r", filepath, "-Y", display_filter, "-T", "fields"]
    for f in fields:
        tshark_cmd += ["-e", f]
    tshark_cmd += ["-E", "header=y", "-E", "separator=|"]

    result = subprocess.run(tshark_cmd, capture_output=True, text=True)
    if result.returncode not in (0, 1):
        return FilterResult(
            pattern_id=pattern_id,
            source_file=source_name,
            match_count=0,
            capped=False,
            lines="",
            error=f"tshark error: {result.stderr.strip()}"
        )

    raw_output = result.stdout

    # Count data rows (exclude header line)
    all_lines = raw_output.splitlines(keepends=True)
    data_lines = [l for l in all_lines if l.strip() and not all(
        part.strip().replace(".", "").replace("_", "").isalpha()
        for part in l.split("|")
    )]
    total_matches = max(0, len(all_lines) - 1)  # subtract header row

    # Simple line cap (tshark output has no rg-style context blocks)
    capped = False
    if len(all_lines) > max_lines + 1:  # +1 for header
        header = all_lines[0] if all_lines else ""
        data = all_lines[1:]
        capped_data = data[-max_lines:]
        all_lines = [header] + capped_data
        raw_output = "".join(all_lines)
        capped = True

    # Apply post_process if specified
    if post_process and post_process_search_dirs:
        script_path = _resolve_script(post_process, post_process_search_dirs)
        if script_path:
            raw_output = _run_post_process(script_path, raw_output, filepath)
        else:
            raw_output = f"[WARNING: post_process script '{post_process}' not found]\n" + raw_output

    return FilterResult(
        pattern_id=pattern_id,
        source_file=source_name,
        match_count=total_matches,
        capped=capped,
        lines=raw_output,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _resolve_script(script_name: str, search_dirs: list) -> Optional[str]:
    for d in search_dirs:
        candidate = os.path.join(d, script_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _run_post_process(script_path: str, text: str, source_file: str) -> str:
    import sys
    result = subprocess.run(
        [sys.executable, script_path, "--source-file", source_file],
        input=text,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return f"[WARNING: post_process script failed: {result.stderr.strip()}]\n" + text
    return result.stdout


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Filter PCAP/PCAPNG files using tshark")
    parser.add_argument("--file", required=True, help="Path to the .pcap or .pcapng file")
    parser.add_argument("--filter", required=True, dest="display_filter", help="tshark display filter (e.g. 'sip.Method == \"REGISTER\"')")
    parser.add_argument("--fields", required=True, nargs="+", help="tshark fields to extract (e.g. frame.number frame.time sip.Method)")
    parser.add_argument("--max-lines", type=int, default=200, help="Max output rows (default: 200)")
    args = parser.parse_args()

    try:
        check_dependencies()
    except ToolNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    result = filter_pcap(
        filepath=args.file,
        display_filter=args.display_filter,
        fields=args.fields,
        max_lines=args.max_lines,
    )

    if result.error:
        print(f"ERROR: {result.error}", file=sys.stderr)
        sys.exit(1)

    print(f"# Source: {result.source_file}  |  Packets: {result.match_count}{' (capped)' if result.capped else ''}\n")
    print(result.lines)
