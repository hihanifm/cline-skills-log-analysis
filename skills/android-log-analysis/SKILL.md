---
name: android-log-analysis
description: >-
  Analyzes Android logcat files using ripgrep. Given a log file, zip archive,
  or folder and a workflow config, builds a structured context file and
  generates a final analysis report. Use when asked to filter, analyze, or
  troubleshoot an Android log file.
---

# Android Log Analysis Skill

## What This Skill Does

This skill delegates all mechanical filtering to `context_builder_agent.py` and
all synthesis to `log_synthesizer_agent.py`. Cline's role is just to invoke the
two scripts and present the result.

---

## Step 1 — Ask for Input

If the user has not already provided a log file, zip archive, or folder path, ask for it now.

---

## Step 2 — Build Context

Run the context builder. It handles input resolution (file/folder/zip), pattern
loading, ripgrep filtering, and output — all deterministically.

Resolve the workflow scripts directory:
```
python3 -c "import os; print(os.path.join(os.path.dirname(os.path.abspath('<this_workflow_file>')), 'scripts'))"
```

Then run:
```
python3 <workflow_scripts_dir>/context_builder_agent.py \
  --workflow <path_to_this_workflow_file> \
  --input <user_provided_path>
```

Capture stdout — it prints the path to the generated `context.yaml`.

If exit code is non-zero, show the stderr output and stop.

---

## Step 3 — Synthesize Report

Run the synthesizer against the context file:

```
python3 <workflow_scripts_dir>/log_synthesizer_agent.py \
  --context <context_yaml_path>
```

Capture stdout — it prints the path to the generated report `.md` file.

**If `LLM_BACKEND=cline`** (default when no `.env` or no API key):
The report will contain `<!-- SUMMARY_PROMPT: <id> ... -->` markers.
Fill in each marker: read the log context in the code block above it and replace
the marker with a `**SUMMARY:**` section containing your analysis.

---

## Step 4 — Present Report

Read the final report file and present it to the user.
Tell the user the report path and a brief summary of findings.
