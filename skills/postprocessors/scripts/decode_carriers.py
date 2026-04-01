"""
decode_carriers.py — Replace carrier codes and MCC/MNC pairs with human-readable names.

Handles common US and international carrier abbreviations found in Android logs,
plus MCC/MNC numeric codes used in IMS/RIL entries.

Usage:
    rg ... | python3 decode_carriers.py [--source-file /path/to/log.txt]

Contract: stdin → stdout. --source-file accepted but not used by this script.
"""

import sys
import re
import argparse

# Carrier code substitutions (case-sensitive, longest match first)
CARRIER_CODES = {
    "VZW": "Verizon",
    "VZWIMS": "Verizon-IMS",
    "TMOUS": "T-Mobile-US",
    "TMUS": "T-Mobile-US",
    "ATT": "AT&T",
    "ATTIMS": "AT&T-IMS",
    "SPRINT": "Sprint",
    "USC": "US-Cellular",
    "USCC": "US-Cellular",
    "USCIMS": "US-Cellular-IMS",
    "DTAG": "Deutsche-Telekom",
    "ORANGE": "Orange",
    "VODAFONE": "Vodafone",
    "O2": "O2",
    "EE": "EE-UK",
    "THREE": "Three-UK",
    "SOFTBANK": "SoftBank",
    "DOCOMO": "NTT-Docomo",
    "KDDI": "KDDI",
}

# MCC/MNC to carrier name (common entries)
MCC_MNC = {
    ("310", "410"): "AT&T",
    ("310", "260"): "T-Mobile-US",
    ("311", "480"): "Verizon",
    ("310", "120"): "Sprint",
    ("311", "882"): "US-Cellular",
    ("208", "01"): "Orange-France",
    ("208", "10"): "SFR-France",
    ("234", "30"): "EE-UK",
    ("234", "20"): "Three-UK",
    ("262", "01"): "Deutsche-Telekom",
    ("440", "10"): "NTT-Docomo",
    ("440", "20"): "SoftBank",
    ("440", "50"): "KDDI",
}

# Build a combined regex for carrier codes (longest first to avoid partial matches)
_sorted_codes = sorted(CARRIER_CODES.keys(), key=len, reverse=True)
_carrier_pattern = re.compile(r'\b(' + '|'.join(re.escape(c) for c in _sorted_codes) + r')\b')

# MCC/MNC pattern: mcc<digits>mnc<digits> or mcc=<digits>,mnc=<digits>
_mccmnc_pattern = re.compile(
    r'mcc[=:]?(\d{3})[,\s]*mnc[=:]?(\d{2,3})',
    re.IGNORECASE
)


def decode_line(line):
    # Replace carrier codes
    def replace_code(m):
        code = m.group(1)
        return CARRIER_CODES.get(code, code)

    line = _carrier_pattern.sub(replace_code, line)

    # Replace MCC/MNC pairs
    def replace_mccmnc(m):
        mcc, mnc = m.group(1), m.group(2)
        name = MCC_MNC.get((mcc, mnc)) or MCC_MNC.get((mcc, mnc.lstrip("0")))
        if name:
            return f"mcc={mcc},mnc={mnc}({name})"
        return m.group(0)

    line = _mccmnc_pattern.sub(replace_mccmnc, line)
    return line


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    for line in sys.stdin:
        sys.stdout.write(decode_line(line))


if __name__ == "__main__":
    main()
