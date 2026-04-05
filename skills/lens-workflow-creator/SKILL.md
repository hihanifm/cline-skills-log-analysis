---
name: lens-workflow-creator
description: >-
  Guides a developer through creating a new analysis workflow .md file.
  Discovers available templates, asks which inputs to analyze and which
  templates to apply, and writes a ready-to-run workflow. Depends on
  lens-log-template-creator and lens-pcap-template-creator for creating new templates.
---

# Workflow Creator Skill

## What This Skill Does

Helps a developer author a new workflow markdown file. Workflows are the
top-level entry point for analysis: they define what log/PCAP files to read,
which templates to apply, and what the final report should summarize.

Once created, a workflow is run end-to-end by the `lens-workflow-orchestrator-agent` skill.

---

## Step 1 — Understand the Goal

Ask the developer:
- What are they trying to troubleshoot or analyze? (e.g. "Bluetooth reconnection failures")
- What types of files will they be analyzing? (logcat, bugreport, PCAP, or a mix)

---

## Step 2 — Discover Available Templates

List the contents of `log-templates/log/` and `log-templates/pcap/` in the project repo, and also `~/.cline/skills/lens-template-library/templates/log/` and `~/.cline/skills/lens-template-library/templates/pcap/` for shared defaults. For each YAML file
found, read its `id` and `description` fields and show the developer a summary:

```
Log templates:
  - wakelock   — WakeLock acquire/release and leak detection
  - power      — PowerManager, BatteryStats, and battery drain patterns
  - ril        — Radio Interface Layer events and errors
  - ims-sip    — IMS/SIP registration and call signaling

PCAP templates:
  - sip        — SIP signaling patterns for IMS/VoLTE analysis
  - dns        — DNS query/response and error patterns
  - http       — HTTP/HTTPS request and response patterns
```

Ask: "Do any of these cover what you need, or do you need new templates?"

- If they need **new log templates** → tell them to run `lens-log-template-creator` first, then come back.
- If they need **new PCAP templates** → tell them to run `lens-pcap-template-creator` first, then come back.
- Otherwise continue.

---

## Step 3 — Gather Workflow Metadata

Ask for:
- **Workflow name** — a short slug with no spaces (e.g. `bluetooth-drops`). Used as the filename and output directory name.
- **Description** — one sentence describing what this workflow analyzes.

---

## Step 4 — Define Input Entries

For each type of input file the developer wants to analyze, ask:

- **File glob** — pattern to match input files (e.g. `logcat*.txt`, `*.pcap`)
- **Templates to include** — which templates from Step 2 apply to this input type. List them as `include:` paths.

All patterns must be defined in template library files — there are no inline patterns in workflows. If the developer needs a new pattern that doesn't exist yet, tell them to run `lens-log-template-creator` or `lens-pcap-template-creator` first to create a proper template file, then come back.

Ask: "Do you want to add another input type?" Repeat until done.

---

## Step 5 — Final Summary Prompt

Ask the developer: "What should the final report conclude? What overall question
should the AI answer after seeing all the pattern matches?"

This becomes the `final_summary_prompt`. If they're unsure, suggest a default:

> Based on all pattern findings above, provide a concise troubleshooting summary
> including: (1) most likely root cause, (2) the top suspicious events with
> timestamps, (3) recommended next steps for investigation.

---

## Step 6 — Write the Workflow File

Write the workflow to `.clinerules/workflows/<name>.md` in the project repo using this structure:

```markdown
---
workflow: <name>
skill: lens-workflow-orchestrator-agent
description: <description>

default_max_lines: 200

input:
  - path: "<glob>"
    include:
      - log-templates/log/<template>.yaml

final_summary_prompt: >
  <final_summary_prompt>
---

# <Workflow Title>

<One paragraph describing what this workflow analyzes, what files it expects,
and when a developer should use it.>
```

The skill type (log vs PCAP) is declared inside each template file — workflows do not specify it. Each input entry is just a file glob plus a list of templates to apply.

---

## Step 7 — Show Next Steps

Tell the developer:

> Workflow written to `.clinerules/workflows/<name>.md`.
>
> Commit this file (along with any `log-templates/` and `log-lens-postprocessors/` you created)
> so colleagues can run the same workflow on their machines.
>
> To run it, invoke the `lens-workflow-orchestrator-agent` skill and point it at this workflow file.
