---
name: lens-postprocessors
description: >-
  Collection of post-processing scripts that transform raw filter output
  (ripgrep lines or tshark rows) into structured, human-readable form before
  LLM synthesis. Referenced by name via post_process: in template pattern
  definitions. Also use this skill to create a new post-processor script.
---

# Postprocessors Skill

## What This Skill Does

Each script in this skill reads raw filter output from stdin and writes
enriched output to stdout. They are invoked automatically by the
`lens-workflow-orchestrator-agent` pipeline when a template pattern specifies
`post_process: <script_name>`.

---

## Available Post-Processors

### `decode_wakelock.py`
**Pairs with:** `wakelock` templates (`post_process: decode_wakelock.py`)

Pairs WakeLock `acquire` / `release` events by tag name. Computes hold
durations, flags holds longer than 60 seconds as long holds, and identifies
unpaired acquires as potential leaks. Appends a `WAKELOCK ANALYSIS` summary
section to the output.

---

### `decode_ril.py`
**Pairs with:** `ril` templates (`post_process: decode_ril.py`)

Translates RIL (Radio Interface Layer) numeric request IDs, PDP failure
codes, and network registration state codes into their symbolic names.
Appends a `RIL CODE LEGEND` section listing every code found and its meaning.

---

### `decode_carriers.py`
**Pairs with:** IMS/carrier templates (`post_process: decode_carriers.py`)

Decodes carrier and MCC/MNC numeric codes into carrier names and country
identifiers. Useful for multi-SIM and roaming analysis in emergency call
and IMS workflows.

---

### `decode_timestamps.py`
**Pairs with:** any log template requiring timestamp normalization

Normalizes Android logcat timestamp formats and computes relative time
deltas between consecutive events. Useful when correlating events across
different log sources.

---

### `decode_sip.py`
**Pairs with:** `sip` PCAP templates (`post_process: decode_sip.py`)

Reformats tshark pipe-delimited SIP field output into a human-readable
call flow table. Groups messages by Call-ID, shows method/response sequence
with timing, and highlights error responses (4xx/5xx/6xx).

---

## Creating a New Post-Processor

### Step 1 — Understand the Transformation

Before writing, clarify:
- What template pattern will this pair with?
- What does the raw filter output look like? (log lines, tshark pipe-delimited rows, etc.)
- What should the output look like? (paired events, decoded codes, reformatted table, etc.)

### Step 2 — Choose a Name

Follow the convention: `decode_<feature>.py`
(e.g. `decode_bluetooth.py`, `decode_gps.py`, `decode_rtp.py`)

### Step 3 — Write the Script

Write `log-lens-postprocessors/<name>.py` in the project repo root following this contract:

**Required:**
- Reads from `sys.stdin`
- Writes to `sys.stdout`
- Progress/debug messages go to `sys.stderr`
- No external dependencies — stdlib only

**Optional but recommended:**
- Accept `--source-file <path>` for multi-pass use
- Append a summary/legend section at the end (see `decode_ril.py` for a
  LEGEND pattern, `decode_wakelock.py` for an ANALYSIS summary pattern)

**Script skeleton:**
```python
"""
decode_<feature>.py — <one-line description>.
"""

import sys


def main():
    lines = sys.stdin.read().splitlines()
    out = []

    for line in lines:
        # transform line
        out.append(line)

    # optional: append summary section
    # out.append("")
    # out.append("=== FEATURE ANALYSIS ===")

    print("\n".join(out))


if __name__ == "__main__":
    main()
```

### Step 4 — Test (if sample input available)

```
echo "<sample_lines>" | python3 skills/lens-postprocessors/scripts/<name>.py
```

### Step 5 — Wire It Up

Reference it in your template pattern:
```yaml
post_process: <name>.py
```

Commit `log-lens-postprocessors/<name>.py` to your project repo so colleagues
can use it too. No deployment needed — the pipeline finds it automatically.
