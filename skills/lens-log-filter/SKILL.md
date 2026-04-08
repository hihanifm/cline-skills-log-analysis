---

## name: lens-log-filter

description: >-
  Filters Android logcat files using ripgrep and a regex pattern. Use directly
  when you want to extract matching lines from a log file without running a full
  workflow. Can also be invoked by the lens-workflow-orchestrator-agent skill automatically.

# Android Log Analysis Skill

## What This Skill Does

Filters a single Android log file using ripgrep. Extracts lines matching a
regex pattern, with optional surrounding context lines. Output is capped to
a configurable maximum.

---

## Step 1 — Ask for Input

Ask the user for:

- **Log file path** (logcat `.txt` or similar)
- **Pattern** — regex to match (e.g. `WakeLock.*(acquire|release)`)
- **Context lines** (optional, default 0) — lines before/after each match
- **Max lines** (optional, default 200) — cap on output lines

---

## Step 2 — Run Filter

Resolve the scripts directory relative to this skill file, then run:

```
python3 <skill_scripts_dir>/log_filter.py \
  --file <log_file> \
  --pattern "<regex>" \
  [--context-lines N] \
  [--max-lines N]
```

---

## Step 3 — Present Output

Show the filtered lines to the user. Include the match count and source file.