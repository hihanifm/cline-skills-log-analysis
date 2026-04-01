# Android Log & PCAP Analysis — Cline Skills + Workflows

## Context
Building a cross-platform Android log and PCAP analysis system. Users invoke a Cline workflow (e.g. `/battery-troubleshooting.md`), provide a log file/zip/folder, and get a structured filtered output file that Cline progressively builds and then summarizes with LLM.

---

## Architecture

```
Workflow (.md)               → declares what to filter, input files, output path, prompts
Pattern YAML                 → patterns + descriptions; composes shared templates from skill
android-log-analysis skill   → owns HOW for logs: checks rg, handles input, writes output
android-pcap-analysis skill  → owns HOW for pcaps: checks tshark, handles input, writes output
Output file (.txt)           → built progressively; filtered lines + per-pattern summaries + final summary
```

---

## File Structure

```
/Users/hanifm/work/cline-skills-log-analysis/
├── PLAN.md
├── README.md
├── skill/
│   ├── android-log-analysis/
│   │   ├── SKILL.md
│   │   ├── patterns/
│   │   │   ├── wakelock.yaml
│   │   │   ├── power.yaml
│   │   │   ├── ims-sip.yaml
│   │   │   └── ril.yaml
│   │   └── scripts/
│   │       ├── decode_carriers.py
│   │       ├── decode_timestamps.py
│   │       └── tail_lines.py
│   └── android-pcap-analysis/
│       ├── SKILL.md
│       ├── patterns/
│       │   ├── sip.yaml
│       │   ├── dns.yaml
│       │   └── http.yaml
│       └── scripts/
│           ├── decode_sip.py
│           └── tail_lines.py
└── workflows/
    ├── battery-troubleshooting.md
    ├── emergency-call-troubleshooting.md
    ├── ims-pcap-troubleshooting.md
    └── scripts/
        ├── decode_wakelock.py
        └── decode_ril.py
```

**Install targets:**
```
~/.cline/skills/android-log-analysis/    ← skill/android-log-analysis/
~/.cline/skills/android-pcap-analysis/   ← skill/android-pcap-analysis/
.clinerules/workflows/                   ← workflows/
```

---

## Workflow File Format (single .md — frontmatter + instructions)

```markdown
---
workflow: battery-troubleshooting
description: Battery drain and power management analysis

output:
  dir: ./battery-analysis-output        # relative to log file location
  filename: "battery_{{timestamp}}.txt"

default_max_lines: 200                  # cap per pattern; overridable per pattern

input:
  - path: "logcat*.txt"                 # each input has its own patterns
    include: [wakelock, power]
    templates:
      - id: high_drain
        pattern: "drain_rate.*[5-9][0-9]%"
        context_lines: 5
        max_lines: 100                  # optional per-pattern override
        description: >
          Abnormally high drain rate (>50%). Indicates aggressive background
          activity or a hardware issue.
        post_process: scripts/decode_drain.py
        summary_prompt: >
          Identify the highest drain rate events. Note timestamps and
          any correlating wakelocks or services active at the time.

  - path: "bugreport*.txt"
    include: [ril]
    templates:
      - id: ril_errors
        pattern: "RIL.*(error|fail|exception)"
        context_lines: 3
        description: RIL layer errors and failures.

final_summary_prompt: >
  Based on all pattern findings above, provide a concise battery
  troubleshooting report: root cause hypothesis, top 3 suspicious
  events with timestamps, and recommended next steps.
---

# Battery Troubleshooting

1. Ask the user for the log file/zip/folder path if not already provided.
2. For each input entry, resolve matching files then run its patterns.
3. For each pattern, write filtered lines to output file. If pattern has
   a summary_prompt, append an LLM summary after the filtered lines.
4. At the end, run final_summary_prompt across all pattern summaries.
5. Save the complete output to the directory specified above.
```

---

## Input Handling

| Input type | Behaviour |
|---|---|
| Single file | Use directly |
| Folder | Match files against `input` globs; run all matches |
| Zip archive | List contents → match against `input` globs → extract only matched files to `<zip_dir>/<archive_name>_extracted/` (skip if already exists) → run all matches |

Each input entry has its own pattern set. Output groups by input, then by pattern:
```
=== INPUT: logcat*.txt ===

---
PATTERN: wakelock_lifecycle  |  SOURCE: logcat_2024-01-14.txt  |  MATCHES: 47
---
...
---
PATTERN: wakelock_lifecycle  |  SOURCE: logcat_2024-01-15.txt  |  MATCHES: 12
---
...

=== INPUT: bugreport*.txt ===

---
PATTERN: ril_errors  |  SOURCE: bugreport.txt  |  MATCHES: 8
---
...
```

Zip extraction: `unzip -j archive.zip "<matched_file>" -d <extract_dir>/`

---

## Shared Pattern Templates

### Log — `skill/android-log-analysis/patterns/`

```yaml
# wakelock.yaml
id: wakelock
templates:
  - id: wakelock_lifecycle
    pattern: "WakeLock.*(acquire|release|LEAK)"
    context_lines: 5
    description: >
      WakeLock acquire/release cycles. LEAK = acquired but never released —
      common cause of battery drain.
    post_process: decode_wakelock.py

  - id: wakelock_timeout
    pattern: "WakeLock.*timeout"
    context_lines: 3
    description: WakeLock timeout events — may indicate stuck wakelocks.
```

### PCAP — `skill/android-pcap-analysis/patterns/`

```yaml
# sip.yaml
id: sip
templates:
  - id: sip_transactions
    filter: "sip.Method"
    fields: [frame.number, frame.time, sip.Method, sip.r-uri, sip.Status-Code]
    description: >
      SIP transaction request/response lines — full signaling flow
      (INVITE, REGISTER, BYE, ACK and responses).
    post_process: decode_sip.py

  - id: sip_errors
    filter: "sip.Status-Code >= 400"
    fields: [frame.number, frame.time, sip.Status-Code, sip.Status-Phrase]
    description: SIP error responses (4xx, 5xx, 6xx).
```

---

## Output File Format

```
=== INPUT: logcat*.txt ===

---
PATTERN: wakelock_lifecycle  |  SOURCE: logcat.txt  |  MATCHES: 1243 (showing last 200)
WakeLock acquire/release cycles. LEAK = acquired but never released.
---

337-  01-15 10:23:11 D WakeLock: acquire tag=email_sync
338-  01-15 10:23:12 D BatteryStats: wakelocks=1
339:  01-15 10:23:15 W WakeLock: LEAK detected tag=email_sync
340-  01-15 10:23:16 D BatteryStats: drain_rate=4.2%/hr

SUMMARY:
Found 2 leaked wakelocks: email_sync (held 4m 12s), location_update (held 8m 3s — suspicious).

---
PATTERN: high_drain  |  SOURCE: logcat.txt  |  MATCHES: 0
---

[No matches found]

---
FINAL SUMMARY
---
Root cause: location_update service holding wakelock for extended periods.
Top 3 events: ...
Recommended next steps: ...
```

---

## Skills

### `android-log-analysis` SKILL.md instructions

1. Check `rg` installed → if not, print install instructions (brew/apt/winget) and stop
2. Resolve patterns: merge `include` templates + inline `patterns` from each input entry
3. Handle input: detect file/folder/zip, resolve `input` globs, extract if needed
4. For each input entry → each pattern × each matched source file:
   - Run: `rg --context <N> --line-number --no-heading "<pattern>" <file> | python3 tail_lines.py --max-lines <M>`
   - If `post_process`: pipe through `python3 <script> --source-file <file>`
   - Write section header + output to file
   - If `summary_prompt`: read filtered output, generate LLM summary, append to file
5. Run `final_summary_prompt` across all summaries, append to file
6. Report output file path

### `android-pcap-analysis` SKILL.md instructions

Same flow, replacing rg with:
```
tshark -r <pcap> -Y "<filter>" -T fields -e <field>... -E header=y | python3 tail_lines.py --max-lines <M>
```
Check `tshark` installed → if not, print install instructions (brew/apt/wireshark.org) and stop.

---

## Post-processing Scripts

**Script resolution**: skill checks `workflows/scripts/` first, then `skill/<name>/scripts/`. Referenced by filename only in pattern YAML.

**Contract**: stdin → stdout, optional `--source-file <path>` for multi-pass access.

| Script | Location | Purpose |
|---|---|---|
| `tail_lines.py` | both skill scripts/ | Cross-platform `tail -n` via circular buffer |
| `decode_carriers.py` | log skill scripts/ | VZW→Verizon, TMOUS→T-Mobile, MCC/MNC decode |
| `decode_timestamps.py` | log skill scripts/ | Normalize timestamps to ISO 8601 |
| `decode_sip.py` | pcap skill scripts/ | tshark SIP output → readable call flow table |
| `decode_wakelock.py` | workflows/scripts/ | Pair acquire/release, flag leaks, compute durations |
| `decode_ril.py` | workflows/scripts/ | RIL numeric codes → human-readable strings |

**Max lines cap resolution (most specific wins):**
per-pattern `max_lines` → workflow `default_max_lines` → skill default `200`

---

## Files to Create

**Log skill:**
1. `skill/android-log-analysis/SKILL.md`
2. `skill/android-log-analysis/patterns/wakelock.yaml`
3. `skill/android-log-analysis/patterns/power.yaml`
4. `skill/android-log-analysis/patterns/ims-sip.yaml`
5. `skill/android-log-analysis/patterns/ril.yaml`
6. `skill/android-log-analysis/scripts/decode_carriers.py`
7. `skill/android-log-analysis/scripts/decode_timestamps.py`
8. `skill/android-log-analysis/scripts/tail_lines.py`

**PCAP skill:**
9. `skill/android-pcap-analysis/SKILL.md`
10. `skill/android-pcap-analysis/patterns/sip.yaml`
11. `skill/android-pcap-analysis/patterns/dns.yaml`
12. `skill/android-pcap-analysis/patterns/http.yaml`
13. `skill/android-pcap-analysis/scripts/decode_sip.py`
14. `skill/android-pcap-analysis/scripts/tail_lines.py`

**Workflows:**
15. `workflows/battery-troubleshooting.md`
16. `workflows/emergency-call-troubleshooting.md`
17. `workflows/ims-pcap-troubleshooting.md`
18. `workflows/scripts/decode_wakelock.py`
19. `workflows/scripts/decode_ril.py`

**Docs:**
20. `README.md`

---

## Verification

1. Install skills + workflows to their targets
2. `/battery-troubleshooting.md` → provide a logcat.txt → verify output file has correct sections, summaries, final summary
3. `/emergency-call-troubleshooting.md` → provide logcat in a zip → verify zip extraction + filtering
4. `/ims-pcap-troubleshooting.md` → provide a .pcap → verify tshark output + SIP call flow table
5. Test max_lines cap: use a log with 1000+ wakelock matches → verify output shows last 200
