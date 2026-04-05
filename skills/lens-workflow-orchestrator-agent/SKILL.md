---
name: lens-workflow-orchestrator-agent
description: >-
  Runs a full analysis workflow against log files, PCAP/PCAPNG captures, zip
  archives, or folders. Given a workflow config file and an input path, builds
  a structured context file then synthesizes a final report. Use when asked to
  analyze or troubleshoot using a named workflow (battery, emergency-call,
  ims-pcap, etc.).
---

# Workflow Orchestrator Skill

## What This Skill Does

This skill delegates all mechanical filtering to `context_builder_agent.py` and
all synthesis to `log_synthesizer_agent.py`. Cline's role is just to invoke the
two scripts and present the result.

The context builder auto-detects whether to use ripgrep (logs) or tshark (PCAP)
based on the pattern structure defined in the workflow file — no manual selection
needed.

Workflow `include:` entries accept paths to template YAML files, resolved relative
to the workflow file. This means anyone can bring their own templates from any
location and reference them by path.

---

## Step 1 — Ask for Input

If the user has not already provided:
- A **workflow file** path (or workflow name to resolve to a path), and
- An **input path** (log file, PCAP/PCAPNG file, zip archive, or folder)

Ask for them now.

---

## Step 2 — Build Context

Run the context builder. It handles input resolution (file/folder/zip), pattern
loading, filtering, and output — all deterministically.

The agent scripts live in `~/.cline/skills/lens-workflow-orchestrator-agent/scripts/`.

```
python3 ~/.cline/skills/lens-workflow-orchestrator-agent/scripts/context_builder_agent.py \
  --workflow <path_to_workflow_file> \
  --input <user_provided_path>
```

Capture stdout — it prints the path to the generated `log-context.md`.

If exit code is non-zero, show the stderr output and stop.

---

## Step 3 — Synthesize Report

Run the synthesizer against the context file:

```
python3 ~/.cline/skills/lens-workflow-orchestrator-agent/scripts/log_synthesizer_agent.py \
  --context <context_txt_path>
```

Capture stdout — it prints the path to the generated report `.md` file.

**If `LLM_BACKEND=cline`** (default when no `.env` or no API key):
The report will contain `<!-- SUMMARY_PROMPT: <id> ... -->` markers.
Fill in each marker: read the context in the code block above it and replace
the marker with a `**SUMMARY:**` section containing your analysis.

After filling all markers, copy the content of the `## FINAL SUMMARY` section
from `report.md` and write it to `summary.md` in the same directory — do not
remove it from `report.md`. Use this header for `summary.md`:

```
# <workflow-name> — Summary

**Input:** `<input_path>`
**Generated:** <timestamp>

<final summary content>
```

---

## Step 4 — Present Report

Read `summary.md` and present it to the user.
Tell the user both file paths (`report.md` for full details, `summary.md` for the summary).
