---
name: template-engine
description: >-
  Applies a template YAML directly to a log or pcap file, running each filter
  definition in the template against the input. Use when you want to apply a
  template to a file without running a full workflow. Also used internally by
  the workflow-orchestrator skill.
---

# Template Engine Skill

## What This Skill Does

Loads a template YAML file and applies every filter entry in it to a single
input file (log or pcap). Auto-detects whether to use ripgrep or tshark based
on the template's pattern structure.

---

## Step 1 — Ask for Input

Ask the user for:
- **Template path** — path to a `.yaml` template file (e.g. `templates/log/wakelock.yaml`)
- **Input file** — log or pcap file to apply it to
- **Skill** (optional) — `android-log-analysis` or `android-pcap-analysis`; auto-detected if omitted
- **Max lines** (optional, default 200)

---

## Step 2 — Run Template

Resolve the scripts directory relative to this skill file, then run:

```
python3 <skill_scripts_dir>/template_runner.py \
  --template <template_path> \
  --file <input_file> \
  [--skill android-log-analysis] \
  [--max-lines 200]
```

---

## Step 3 — Present Output

Show the matched sections to the user, one per template entry.
Include match counts and source file.
