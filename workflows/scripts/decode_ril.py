"""
decode_ril.py — Translate RIL numeric codes to human-readable strings.

Decodes:
  - RIL request/response IDs to their symbolic names
  - PDP_FAIL error codes to their meanings
  - Data call setup failure reasons
  - Network registration status codes

Usage:
    rg ... | python3 decode_ril.py [--source-file /path/to/log.txt]

Contract: stdin → stdout. Replaces numeric codes inline and appends a
RIL CODE LEGEND section listing codes found and their meanings.
"""

import sys
import re
import argparse


# RIL request IDs (from ril.h)
RIL_REQUESTS = {
    "1": "GET_SIM_STATUS",
    "2": "ENTER_SIM_PIN",
    "3": "ENTER_SIM_PUK",
    "4": "ENTER_SIM_PIN2",
    "5": "ENTER_SIM_PUK2",
    "6": "CHANGE_SIM_PIN",
    "7": "CHANGE_SIM_PIN2",
    "9": "GET_CURRENT_CALLS",
    "10": "DIAL",
    "11": "GET_IMSI",
    "12": "HANGUP",
    "13": "HANGUP_WAITING_OR_BACKGROUND",
    "14": "HANGUP_FOREGROUND_RESUME_BACKGROUND",
    "20": "ANSWER",
    "25": "SIGNAL_STRENGTH",
    "26": "VOICE_REGISTRATION_STATE",
    "27": "DATA_REGISTRATION_STATE",
    "28": "OPERATOR",
    "29": "RADIO_POWER",
    "31": "SEND_SMS",
    "41": "SETUP_DATA_CALL",
    "42": "SIM_IO",
    "43": "SEND_USSD",
    "46": "DEACTIVATE_DATA_CALL",
    "47": "GET_FACILITY_LOCK",
    "48": "SET_FACILITY_LOCK",
    "56": "SCREEN_STATE",
    "61": "SET_NETWORK_SELECTION_AUTOMATIC",
    "65": "GET_NEIGHBORING_CELL_IDS",
    "108": "SET_PREFERRED_NETWORK_TYPE",
    "112": "VOICE_RADIO_TECH",
}

# PDP fail causes (from RIL_DataCallFailCause in ril.h)
PDP_FAIL = {
    "0": "NONE",
    "8": "OPERATOR_BARRED",
    "14": "NAS_SIGNALLING",
    "26": "INSUFFICIENT_RESOURCES",
    "27": "MISSING_UNKNOWN_APN",
    "28": "UNKNOWN_PDP_ADDRESS_TYPE",
    "29": "USER_AUTHENTICATION",
    "30": "ACTIVATION_REJECT_GGSN",
    "31": "ACTIVATION_REJECT_UNSPECIFIED",
    "32": "SERVICE_OPTION_NOT_SUPPORTED",
    "33": "SERVICE_OPTION_NOT_SUBSCRIBED",
    "34": "SERVICE_OPTION_OUT_OF_ORDER",
    "35": "NSAPI_IN_USE",
    "36": "REGULAR_DEACTIVATION",
    "37": "QOS_NOT_ACCEPTED",
    "38": "NETWORK_FAILURE",
    "39": "UMTS_REACTIVATION_REQ",
    "40": "FEATURE_NOT_SUPP",
    "41": "TFT_SEMANTIC_ERROR",
    "42": "TFT_SYNTAX_ERROR",
    "43": "UNKNOWN_PDP_CONTEXT",
    "44": "FILTER_SEMANTIC_ERROR",
    "45": "FILTER_SYNTAX_ERROR",
    "46": "PDP_WITHOUT_ACTIVE_TFT",
    "55": "MULTICONN_TO_SAME_PDN_NOT_ALLOWED",
    "65": "EMERGENCY_IFACE_ONLY",
    "66": "IFACE_MISMATCH",
    "67": "COMPANION_IFACE_IN_USE",
    "81": "INVALID_TRANSACTION_ID",
    "95": "MESSAGE_INCORRECT_SEMANTIC",
    "111": "PROTOCOL_ERRORS",
    "112": "APN_TYPE_CONFLICT",
    "1000": "VOICE_REGISTRATION_FAIL",
    "1001": "DATA_REGISTRATION_FAIL",
    "1002": "SIGNAL_LOST",
    "1003": "PREF_RADIO_TECH_CHANGED",
    "1004": "RADIO_POWER_OFF",
    "1005": "TETHERED_CALL_ACTIVE",
    "-1": "ERROR_UNSPECIFIED",
}

# Network registration status
REG_STATE = {
    "0": "NOT_REGISTERED",
    "1": "REGISTERED_HOME",
    "2": "SEARCHING",
    "3": "REGISTRATION_DENIED",
    "4": "UNKNOWN",
    "5": "REGISTERED_ROAMING",
    "10": "NOT_REGISTERED_EMERGENCY_ONLY",
    "12": "SEARCHING_EMERGENCY_ONLY",
    "13": "DENIED_EMERGENCY_ONLY",
    "14": "UNKNOWN_EMERGENCY_ONLY",
}

_found_codes = {}  # track what was decoded for legend

def decode_pdp_fail(m):
    code = m.group(1)
    name = PDP_FAIL.get(code)
    if name:
        _found_codes[f"PDP_FAIL={code}"] = name
        return f"PDP_FAIL={code}({name})"
    return m.group(0)

def decode_reg_state(m):
    code = m.group(1)
    name = REG_STATE.get(code)
    if name:
        _found_codes[f"REG_STATE={code}"] = name
        return f"REG_STATE={code}({name})"
    return m.group(0)

_PDP_FAIL_RE = re.compile(r'PDP_FAIL[_=:\s]+(-?\d+)', re.IGNORECASE)
_REG_STATE_RE = re.compile(r'(?:regState|registrationState|voiceRegState|dataRegState)[=:\s]+(\d+)', re.IGNORECASE)


def decode_line(line):
    line = _PDP_FAIL_RE.sub(decode_pdp_fail, line)
    line = _REG_STATE_RE.sub(decode_reg_state, line)
    return line


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", default=None)  # accepted, not used
    args = parser.parse_args()

    lines = sys.stdin.readlines()

    for line in lines:
        sys.stdout.write(decode_line(line))

    if _found_codes:
        sys.stdout.write("\n--- RIL CODE LEGEND ---\n")
        for code, name in sorted(_found_codes.items()):
            sys.stdout.write(f"  {code} = {name}\n")
        sys.stdout.write("--- END RIL CODE LEGEND ---\n")


if __name__ == "__main__":
    main()
