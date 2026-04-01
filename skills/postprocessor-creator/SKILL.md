---
name: postprocessor-creator
description: >-
  Guides a developer through writing a new post-processor script for the
  postprocessors skill. Asks what the raw filter output looks like, what
  transformation is needed, writes the script to skills/postprocessors/scripts/,
  and updates the postprocessors SKILL.md catalogue. Use after log-template-creator
  or pcap-template-creator when raw filter output needs decoding or enrichment.
---

# Postprocessor Creator Skill

## What This Skill Does

Helps a developer write a new post-processing script. Post-processors sit
between the filter step (ripgrep/tshark) and the LLM synthesis step. They
read raw filter output from stdin and write enriched output to stdout.

Once written, the script is referenced by filename in a template pattern:
```yaml
post_process: decode_myfeature.py
```

---

## Step 1 — Understand the Transformation

Ask the developer:
- What template pattern will this post-processor pair with?
- What does the raw filter output look like? (log lines with timestamps, tshark pipe-delimited rows, etc.)
- What should the output look like? (paired events, decoded codes, reformatted table, etc.)
- Does the developer have a sample of the raw input to work from?

---

## Step 2 — Choose a Name

Script name should follow the convention: `decode_<feature>.py`
(e.g. `decode_bluetooth.py`, `decode_gps.py`, `decode_rtp.py`).

Ask the developer to confirm the name.

---

## Step 3 — Write the Script

Write `skills/postprocessors/scripts/<name>.py` following this contract:

**Required:**
- Reads from `sys.stdin`
- Writes to `sys.stdout`
- All progress/debug messages go to `sys.stderr`
- No external dependencies — stdlib only

**Optional but recommended:**
- Accept `--source-file <path>` argument for multi-pass use (read the file
  directly instead of stdin, useful when the script needs two passes)
- Append a summary/legend section at the end of output (see `decode_ril.py`
  for a LEGEND pattern, `decode_wakelock.py` for a ANALYSIS summary pattern)

**Script skeleton:**
```python
"""
decode_<feature>.py — <one-line description>.

<What it reads, what it produces, what it appends.>
"""

import re
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
    # out.append(...)

    print("\n".join(out))


if __name__ == "__main__":
    main()
```

Use the existing scripts in `skills/postprocessors/scripts/` as reference
for patterns like paired event detection (`decode_wakelock.py`) or code
lookup tables (`decode_ril.py`).

---

## Step 4 — Test the Script (if sample input provided)

If the developer provided sample raw filter output, pipe it through the
new script and show the result:

```
echo "<sample_lines>" | python3 skills/postprocessors/scripts/<name>.py
```

Iterate until the output looks correct.

---

## Step 5 — Update the Postprocessors Catalogue

Add an entry to `skills/postprocessors/SKILL.md` under
**Available Post-Processors**:

```markdown
### `<name>.py`
**Pairs with:** `<template_id>` templates (`post_process: <name>.py`)

<One paragraph describing what it decodes, what it appends, and what
a developer or analyst should look for in the output.>
```

---

## Step 6 — Show Next Steps

Tell the developer:

> Script written to `skills/postprocessors/scripts/<name>.py`.
>
> To use it, add to your template pattern:
> ```yaml
> post_process: <name>.py
> ```
>
> Run `python3 setup.py --skip-cli` to deploy, then test end-to-end
> with the `workflow-orchestrator` skill.
