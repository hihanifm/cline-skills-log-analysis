"""
decode_timestamps.py — Normalize Android log timestamps to ISO 8601.

Android logs use several timestamp formats:
  - Logcat: MM-DD HH:MM:SS.mmm  (e.g. 01-15 10:23:15.887)
  - Epoch milliseconds: 13-digit number (e.g. 1705312995887)
  - Epoch seconds: 10-digit number (e.g. 1705312995)
  - Uptime seconds: floating point (e.g. 12345.678)

Normalized output: YYYY-MM-DDTHH:MM:SS.mmm (assumes current year for logcat format).

Usage:
    rg ... | python3 decode_timestamps.py [--year 2024] [--source-file /path/to/log.txt]

Contract: stdin → stdout.
"""

import sys
import re
import argparse
from datetime import datetime, timezone


# Logcat format: MM-DD HH:MM:SS.mmm
_LOGCAT_TS = re.compile(
    r'\b(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})\b'
)

# Epoch milliseconds (13 digits)
_EPOCH_MS = re.compile(r'\b(\d{13})\b')

# Epoch seconds (10 digits) — only replace when clearly a timestamp context
_EPOCH_S = re.compile(r'\btime[=:\s]+(\d{10})\b', re.IGNORECASE)


def make_logcat_replacer(year):
    def replace(m):
        try:
            month, day, hour, minute, second, ms = (int(x) for x in m.groups())
            dt = datetime(year, month, day, hour, minute, second, ms * 1000)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}"
        except ValueError:
            return m.group(0)
    return replace


def replace_epoch_ms(m):
    try:
        ts = int(m.group(1)) / 1000.0
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(ts * 1000) % 1000:03d}Z"
    except (ValueError, OSError):
        return m.group(0)


def replace_epoch_s(m):
    try:
        ts = int(m.group(1))
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return f"time={dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    except (ValueError, OSError):
        return m.group(0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=datetime.now().year,
                        help="Year to use for MM-DD logcat timestamps (default: current year)")
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    logcat_replacer = make_logcat_replacer(args.year)

    for line in sys.stdin:
        line = _LOGCAT_TS.sub(logcat_replacer, line)
        line = _EPOCH_MS.sub(replace_epoch_ms, line)
        line = _EPOCH_S.sub(replace_epoch_s, line)
        sys.stdout.write(line)


if __name__ == "__main__":
    main()
