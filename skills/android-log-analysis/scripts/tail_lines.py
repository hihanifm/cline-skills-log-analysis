"""
tail_lines.py — Cross-platform tail -n replacement.

Reads stdin line by line using a circular buffer, outputs the last N lines.
Used to cap rg/tshark output to avoid overwhelming LLM context.

Usage:
    rg ... | python3 tail_lines.py --max-lines 200
    tshark ... | python3 tail_lines.py --max-lines 100

Contract: stdin → stdout. Ignores --source-file if passed (accepted for pipeline compat).
"""

import sys
import argparse
import collections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-lines", type=int, default=200)
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    buf = collections.deque(maxlen=args.max_lines)
    total = 0

    for line in sys.stdin:
        buf.append(line)
        total += 1

    if total > args.max_lines:
        sys.stderr.write(f"[tail_lines] {total} lines received, showing last {args.max_lines}\n")

    sys.stdout.writelines(buf)


if __name__ == "__main__":
    main()
