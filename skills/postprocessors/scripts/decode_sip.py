"""
decode_sip.py — Format tshark SIP output into a readable call flow table.

Reads pipe-separated tshark field output (produced with -E separator="|")
and reformats it as an aligned call flow table with direction arrows.

Expected input columns (from sip.yaml sip_transactions pattern):
  frame.number | frame.time_relative | ip.src | ip.dst | sip.Method |
  sip.r-uri | sip.Status-Code | sip.Status-Phrase | sip.CSeq

Usage:
    tshark -r cap.pcap -Y "sip" -T fields -e frame.number ... -E separator="|" \
        | python3 decode_sip.py [--source-file cap.pcap]

Contract: stdin → stdout.
"""

import sys
import argparse


def parse_line(line):
    parts = line.rstrip("\n").split("|")
    # Pad to expected number of fields
    while len(parts) < 9:
        parts.append("")
    return {
        "frame": parts[0].strip(),
        "time":  parts[1].strip(),
        "src":   parts[2].strip(),
        "dst":   parts[3].strip(),
        "method": parts[4].strip(),
        "r_uri":  parts[5].strip(),
        "status_code": parts[6].strip(),
        "status_phrase": parts[7].strip(),
        "cseq":  parts[8].strip(),
    }


def format_sip_message(f):
    # Build direction label
    direction = f"{f['src']} → {f['dst']}"

    # Build message label
    if f["method"]:
        msg = f["method"]
        if f["r_uri"]:
            # Truncate long URIs
            uri = f["r_uri"]
            if len(uri) > 60:
                uri = uri[:57] + "..."
            msg += f" {uri}"
    elif f["status_code"]:
        msg = f"{f['status_code']} {f['status_phrase']}"
    else:
        return None  # skip non-SIP rows

    cseq = f"[{f['cseq']}]" if f["cseq"] else ""
    time = f"t={f['time']}s" if f["time"] else ""

    return f"  #{f['frame']:>5}  {time:<18}  {direction:<45}  {msg} {cseq}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    header_printed = False

    for line in sys.stdin:
        line = line.rstrip("\n")
        if not line:
            continue

        # Skip tshark header row if present
        if not header_printed and "frame.number" in line.lower():
            header_printed = True
            continue
        header_printed = True

        f = parse_line(line)
        formatted = format_sip_message(f)
        if formatted:
            sys.stdout.write(formatted + "\n")


if __name__ == "__main__":
    main()
