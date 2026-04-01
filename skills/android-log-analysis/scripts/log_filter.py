"""
log_filter.py — Importable skill module for Android log filtering via ripgrep.

Exposes a clean Python API used by context_builder_agent.py.
No CLI — this is a library, not a standalone script.

Usage (from context_builder_agent.py):
    import sys, os
    sys.path.insert(0, '<skill_dir>/scripts')
    from log_filter import filter_file, count_matches, check_dependencies, ToolNotFoundError
"""

import os
import re
import shutil
import subprocess
import collections
from dataclasses import dataclass, field
from typing import Optional


class ToolNotFoundError(Exception):
    """Raised when a required CLI tool (rg) is not installed."""
    pass


@dataclass
class FilterResult:
    pattern_id: str
    source_file: str
    match_count: int
    capped: bool
    lines: str               # filtered log text (post-processed if applicable)
    error: Optional[str] = None


def check_dependencies():
    """
    Check that ripgrep (rg) is installed.
    Raises ToolNotFoundError with install instructions if missing.
    """
    if shutil.which("rg") is None:
        raise ToolNotFoundError(
            "ripgrep (rg) is not installed or not in PATH.\n"
            "Install instructions:\n"
            "  macOS:          brew install ripgrep\n"
            "  Linux (apt):    sudo apt install ripgrep\n"
            "  Linux (dnf):    sudo dnf install ripgrep\n"
            "  Windows:        winget install BurntSushi.ripgrep.MSVC\n"
        )


def count_matches(filepath: str, pattern: str) -> int:
    """Return total number of lines matching pattern in filepath."""
    result = subprocess.run(
        ["rg", "--count", "-e", pattern, filepath],
        capture_output=True, text=True
    )
    if result.returncode not in (0, 1):
        return 0
    total = 0
    for line in result.stdout.splitlines():
        if ":" in line:
            try:
                total += int(line.rsplit(":", 1)[1])
            except ValueError:
                pass
    return total


def filter_file(
    filepath: str,
    pattern: str,
    pattern_id: str = "pattern",
    context_lines: int = 5,
    max_lines: int = 200,
    post_process: Optional[str] = None,
    post_process_search_dirs: Optional[list] = None,
) -> FilterResult:
    """
    Run rg on filepath, cap output, optionally pipe through post_process script.

    Args:
        filepath:                  Path to the log file.
        pattern:                   ripgrep regex pattern.
        pattern_id:                ID label for this pattern (used in result).
        context_lines:             Lines of context around each match.
        max_lines:                 Max match lines to keep (via tail_lines logic).
        post_process:              Script filename to pipe output through (optional).
        post_process_search_dirs:  Directories to search for post_process script.

    Returns:
        FilterResult with filtered log text and metadata.
    """
    source_name = os.path.basename(filepath)

    # Run rg
    rg_cmd = [
        "rg",
        "--context", str(context_lines),
        "--line-number",
        "--no-heading",
        "-e", pattern,
        filepath,
    ]
    rg_result = subprocess.run(rg_cmd, capture_output=True, text=True)
    if rg_result.returncode not in (0, 1):
        return FilterResult(
            pattern_id=pattern_id,
            source_file=source_name,
            match_count=0,
            capped=False,
            lines="",
            error=f"rg error: {rg_result.stderr.strip()}"
        )

    raw_output = rg_result.stdout
    total_matches = count_matches(filepath, pattern)

    # Apply match-aware cap
    capped_output, was_capped = _cap_rg_output(raw_output, max_lines)

    # Apply post_process if specified
    if post_process and post_process_search_dirs:
        script_path = _resolve_script(post_process, post_process_search_dirs)
        if script_path:
            capped_output = _run_post_process(script_path, capped_output, filepath)
        else:
            # Script not found — use raw output, add warning
            capped_output = f"[WARNING: post_process script '{post_process}' not found]\n" + capped_output

    return FilterResult(
        pattern_id=pattern_id,
        source_file=source_name,
        match_count=total_matches,
        capped=was_capped,
        lines=capped_output,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

_RG_MATCH_RE = re.compile(r"^\d+:")
_RG_CONTEXT_RE = re.compile(r"^\d+-")
_RG_SEP_RE = re.compile(r"^--$")


def _is_rg_format(lines: list) -> bool:
    for line in lines[:20]:
        if _RG_MATCH_RE.match(line) or _RG_CONTEXT_RE.match(line):
            return True
    return False


def _split_into_blocks(lines: list) -> list:
    blocks, current = [], []
    for line in lines:
        if _RG_SEP_RE.match(line.rstrip()):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _count_matches_in_block(block: list) -> int:
    return sum(1 for line in block if _RG_MATCH_RE.match(line))


def _cap_rg_output(raw: str, max_lines: int) -> tuple:
    """Returns (capped_text, was_capped). Caps by match count, preserving context blocks."""
    if not raw:
        return raw, False

    all_lines = raw.splitlines(keepends=True)

    if not _is_rg_format(all_lines):
        # Plain text fallback — simple line cap
        if len(all_lines) <= max_lines:
            return raw, False
        return "".join(all_lines[-max_lines:]), True

    blocks = _split_into_blocks(all_lines)
    total_matches = sum(_count_matches_in_block(b) for b in blocks)

    if total_matches <= max_lines:
        return raw, False

    # Walk from end, keep complete blocks up to budget
    kept = collections.deque()
    kept_count = 0
    for block in reversed(blocks):
        bm = _count_matches_in_block(block)
        if kept_count + bm <= max_lines:
            kept.appendleft(block)
            kept_count += bm
        else:
            remaining = max_lines - kept_count
            partial = []
            for line in reversed(block):
                partial.append(line)
                if _RG_MATCH_RE.match(line):
                    remaining -= 1
                    if remaining <= 0:
                        break
            kept.appendleft(list(reversed(partial)))
            break

    result_parts = []
    first = True
    for block in kept:
        if not first:
            result_parts.append("--\n")
        result_parts.extend(block)
        first = False

    return "".join(result_parts), True


def _resolve_script(script_name: str, search_dirs: list) -> Optional[str]:
    """Find script_name in search_dirs (first match wins)."""
    for d in search_dirs:
        candidate = os.path.join(d, script_name)
        if os.path.isfile(candidate):
            return candidate
    return None


def _run_post_process(script_path: str, text: str, source_file: str) -> str:
    """Pipe text through post_process script. Returns transformed output."""
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
