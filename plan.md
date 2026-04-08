# Plan: Restrict workflow to given input only

## Goal
Prevent Cline from searching for alternative log files (e.g. in parent folders) when the provided input fails. Both the SKILL.md instructions and the Python script must enforce this boundary.

## Files

- `skills/lens-workflow-orchestrator-agent/SKILL.md`
- `skills/lens-workflow-orchestrator-agent/scripts/context_builder_agent.py`

## Steps

### 1. `context_builder_agent.py` — hard-fail on missing input
In `_resolve_input_files`, when the input path does not exist, call `sys.exit(1)` immediately instead of returning `[]`. This turns a silent warning into a hard error that Cline cannot ignore.

### 2. `context_builder_agent.py` — hard-fail on empty folder match
When the input is a directory but no files match the glob, also exit with code 1 (currently it just logs a warning and continues). No files = nothing to do.

### 3. `SKILL.md` — explicit scope restriction
Add a clear instruction before Step 2:
- Work **only** with the exact path the user provided.
- If the script exits non-zero for any reason, show the error and stop.
- Do **not** look in parent directories, sibling directories, or anywhere else.
- Do **not** attempt to locate a log file on the user's behalf.
