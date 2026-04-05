---
name: lens-pcap-filter
description: >-
  Filters PCAP/PCAPNG network capture files using tshark display filters and
  field extraction. Use directly when you want to extract packets without
  running a full workflow. Can also be invoked by the lens-workflow-orchestrator-agent
  skill automatically.
---

# Android PCAP Analysis Skill

## What This Skill Does

Filters a single PCAP or PCAPNG file using tshark. Extracts packets matching a
display filter and outputs specified fields as delimited text. Output is capped
to a configurable maximum.

---

## Step 1 — Ask for Input

Ask the user for:
- **PCAP file path** (`.pcap` or `.pcapng`)
- **Display filter** — tshark display filter (e.g. `sip.Method == "REGISTER"`)
- **Fields** — tshark fields to extract (e.g. `frame.number frame.time sip.Method sip.Status-Code`)
- **Max lines** (optional, default 200) — cap on output rows

---

## Step 2 — Run Filter

Resolve the scripts directory relative to this skill file, then run:

```
python3 <skill_scripts_dir>/pcap_filter.py \
  --file <pcap_file> \
  --filter "<display_filter>" \
  --fields <field1> <field2> ... \
  [--max-lines N]
```

---

## Step 3 — Present Output

Show the extracted fields to the user. Include the packet count and source file.
