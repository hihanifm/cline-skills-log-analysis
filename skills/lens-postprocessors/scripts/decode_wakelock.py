"""
decode_wakelock.py — Pair WakeLock acquire/release events, flag leaks, compute durations.

Reads rg-filtered WakeLock log lines from stdin. Matches acquire/release pairs
by tag name. Reports unpaired acquires as leaks and computes hold durations
for matched pairs.

Usage:
    rg ... | python3 decode_wakelock.py [--source-file /path/to/log.txt]

Contract: stdin → stdout. Outputs the original lines followed by a
WAKELOCK ANALYSIS section with paired events and flagged leaks.
"""

import sys
import re
import argparse
from collections import defaultdict


# Match Android logcat timestamp: MM-DD HH:MM:SS.mmm
_TS_RE = re.compile(r'(\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})')

# WakeLock acquire: tag is usually after "acquire" keyword
_ACQUIRE_RE = re.compile(r'WakeLock.*acquire.*?tag[=:\s]+([^\s,\)]+)', re.IGNORECASE)
_ACQUIRE_SIMPLE = re.compile(r'acquire\s+([^\s,\)]+)', re.IGNORECASE)

# WakeLock release
_RELEASE_RE = re.compile(r'WakeLock.*release.*?tag[=:\s]+([^\s,\)]+)', re.IGNORECASE)
_RELEASE_SIMPLE = re.compile(r'release\s+([^\s,\)]+)', re.IGNORECASE)

# WakeLock LEAK
_LEAK_RE = re.compile(r'WakeLock.*LEAK.*?tag[=:\s]+([^\s,\)]+)', re.IGNORECASE)
_LEAK_SIMPLE = re.compile(r'LEAK\s+([^\s,\)]+)', re.IGNORECASE)


def parse_timestamp_ms(ts_str):
    """Parse MM-DD HH:MM:SS.mmm to milliseconds-of-day (approximate, ignores date)."""
    try:
        time_part = ts_str.split(" ")[1]
        h, m, rest = time_part.split(":")
        s, ms = rest.split(".")
        return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)
    except Exception:
        return None


def extract_tag(line, primary_re, fallback_re):
    m = primary_re.search(line)
    if m:
        return m.group(1).strip('"\'')
    m = fallback_re.search(line)
    if m:
        return m.group(1).strip('"\'')
    return None


def format_duration(ms):
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    elif ms < 3600000:
        return f"{ms/60000:.1f}m"
    else:
        return f"{ms/3600000:.1f}h"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    lines = [l.rstrip("\r\n") + "\n" for l in sys.stdin.readlines()]

    # Pass-through original lines first
    for line in lines:
        sys.stdout.write(line)

    # Parse events
    # pending[tag] = list of (timestamp_ms, line_number, line)
    pending = defaultdict(list)
    paired = []  # (tag, acquire_ts, release_ts, duration_ms)
    leaks = []   # (tag, acquire_ts, line)

    _RG_MATCH = re.compile(r'^\d+:')   # rg match line: <linenum>:<text>
    _RG_CONTEXT = re.compile(r'^\d+-') # rg context line: <linenum>-<text>

    for i, line in enumerate(lines):
        # Detect rg match lines vs context lines by line number prefix
        is_match = bool(_RG_MATCH.match(line))

        ts_match = _TS_RE.search(line)
        ts_ms = parse_timestamp_ms(ts_match.group(1)) if ts_match else None

        if _LEAK_RE.search(line) or _LEAK_SIMPLE.search(line):
            tag = extract_tag(line, _LEAK_RE, _LEAK_SIMPLE) or "unknown"
            leaks.append((tag, ts_match.group(1) if ts_match else "?", line.strip()))
        elif _ACQUIRE_RE.search(line) or (is_match and _ACQUIRE_SIMPLE.search(line)):
            tag = extract_tag(line, _ACQUIRE_RE, _ACQUIRE_SIMPLE) or "unknown"
            pending[tag].append((ts_ms, i, line.strip()))
        elif _RELEASE_RE.search(line) or (is_match and _RELEASE_SIMPLE.search(line)):
            tag = extract_tag(line, _RELEASE_RE, _RELEASE_SIMPLE) or "unknown"
            if pending[tag]:
                acq_ts, acq_idx, acq_line = pending[tag].pop(0)
                duration = (ts_ms - acq_ts) if (ts_ms and acq_ts) else None
                paired.append((tag, acq_ts, ts_ms, duration))
            # else: release without acquire (already released or log truncated)

    # Collect unpaired acquires as leaks
    for tag, events in pending.items():
        for ts_ms, idx, line in events:
            leaks.append((tag, f"ts={ts_ms}" if ts_ms else "?", line))

    # Write analysis summary
    sys.stdout.write("\n--- WAKELOCK ANALYSIS ---\n")

    if paired:
        sys.stdout.write(f"\nPaired acquire/release ({len(paired)} pairs):\n")
        for tag, acq_ts, rel_ts, dur in paired:
            dur_str = format_duration(dur) if dur is not None else "unknown duration"
            flag = " *** LONG HOLD ***" if dur and dur > 60000 else ""
            sys.stdout.write(f"  {tag}: held {dur_str}{flag}\n")

    if leaks:
        sys.stdout.write(f"\nLeaked wakelocks — acquired but never released ({len(leaks)}):\n")
        for tag, ts, line in leaks:
            sys.stdout.write(f"  *** LEAK *** {tag} at {ts}\n")
            sys.stdout.write(f"    {line}\n")
    else:
        sys.stdout.write("\nNo leaked wakelocks detected.\n")

    sys.stdout.write("--- END WAKELOCK ANALYSIS ---\n")


if __name__ == "__main__":
    main()
