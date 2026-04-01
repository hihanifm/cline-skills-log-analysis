---
name: postprocessors
description: >-
  Collection of post-processing scripts that transform raw filter output
  (ripgrep lines or tshark rows) into structured, human-readable form before
  LLM synthesis. Referenced by name via post_process: in template pattern
  definitions. Not invoked directly — used automatically by the pipeline.
---

# Postprocessors Skill

## What This Skill Does

Each script in this skill reads raw filter output from stdin and writes
enriched output to stdout. They are invoked automatically by the
`workflow-orchestrator` pipeline when a template pattern specifies
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

## Adding a New Post-Processor

1. Create `skills/postprocessors/scripts/<name>.py`
2. Script must read from **stdin** and write to **stdout**
3. Optionally accept `--source-file <path>` for multi-pass use
4. Reference it in a template pattern: `post_process: <name>.py`
5. Run `setup.py` to deploy
