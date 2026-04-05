"""
tail_lines.py — Cross-platform tail -n replacement, match-aware.

Reads rg/tshark output from stdin. Keeps the last N *match* lines and their
associated context lines. A match line is detected by rg's format:
  <linenum>:<text>   ← match
  <linenum>-<text>   ← context
  --                 ← separator between match groups

Capping by match count (not total lines) ensures context lines are never
orphaned — we always keep complete match blocks.

Usage:
    rg --context 5 ... | python3 tail_lines.py --max-lines 200
    tshark ... | python3 tail_lines.py --max-lines 100

For tshark output (no rg-style line prefixes), falls back to simple line capping.

Contract: stdin → stdout. Ignores --source-file if passed.
"""

import sys
import re
import argparse
import collections

_MATCH_LINE = re.compile(r'^\d+:')
_CONTEXT_LINE = re.compile(r'^\d+-')
_SEPARATOR = re.compile(r'^--$')


def is_rg_format(lines):
    """Detect if input looks like rg output (has linenum: or linenum- prefixes)."""
    for line in lines[:20]:
        if _MATCH_LINE.match(line) or _CONTEXT_LINE.match(line):
            return True
    return False


def split_into_blocks(lines):
    """Split rg output into match blocks separated by '--'."""
    blocks = []
    current = []
    for line in lines:
        if _SEPARATOR.match(line.rstrip()):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def count_matches_in_block(block):
    return sum(1 for line in block if _MATCH_LINE.match(line))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-lines", type=int, default=200,
                        help="Maximum number of match lines to keep (default: 200)")
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    all_lines = sys.stdin.readlines()

    if not all_lines:
        return

    if not is_rg_format(all_lines):
        # tshark or plain text — simple line cap from the end
        total = len(all_lines)
        if total > args.max_lines:
            sys.stderr.write(
                f"[tail_lines] {total} lines, showing last {args.max_lines}\n"
            )
            all_lines = all_lines[-args.max_lines:]
        sys.stdout.writelines(all_lines)
        return

    # rg format — cap by match count, keeping complete blocks
    blocks = split_into_blocks(all_lines)
    total_matches = sum(count_matches_in_block(b) for b in blocks)

    if total_matches <= args.max_lines:
        sys.stdout.writelines(all_lines)
        return

    # Walk blocks from the end, accumulate until we hit max_lines matches
    sys.stderr.write(
        f"[tail_lines] {total_matches} matches, showing last {args.max_lines}\n"
    )

    kept_blocks = collections.deque()
    kept_matches = 0
    for block in reversed(blocks):
        block_matches = count_matches_in_block(block)
        if kept_matches + block_matches <= args.max_lines:
            kept_blocks.appendleft(block)
            kept_matches += block_matches
        else:
            # Partial block: take lines from end of block up to remaining budget
            remaining = args.max_lines - kept_matches
            partial = []
            for line in reversed(block):
                partial.append(line)
                if _MATCH_LINE.match(line):
                    remaining -= 1
                    if remaining <= 0:
                        break
            kept_blocks.appendleft(list(reversed(partial)))
            break

    first = True
    for block in kept_blocks:
        if not first:
            sys.stdout.write("--\n")
        sys.stdout.writelines(block)
        first = False


if __name__ == "__main__":
    main()
