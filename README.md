# Android Log & PCAP Analysis — Cline Skills + Workflows

Cross-platform Android log and network capture analysis using Cline workflows and skills.

---

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| [ripgrep](https://github.com/BurntSushi/ripgrep) | Log filtering | `brew install ripgrep` / `apt install ripgrep` / `winget install BurntSushi.ripgrep.MSVC` |
| [tshark](https://www.wireshark.org/) | PCAP analysis | `brew install wireshark` / `apt install tshark` / Wireshark installer on Windows |
| Python 3 | Post-processing scripts | Pre-installed on macOS/Linux; [python.org](https://python.org) on Windows |

---

## Install

### Option A — One-step installer (recommended)

Use the bundled `setup.py` script to install CLI tools, skills, and workflows:

```bash
# From the repo root
./setup.py

# Or, to also install workflows into a specific project:
./setup.py --project-dir /path/to/your/project

# Or, if you already have rg/tshark installed and just want skills/workflows:
./setup.py --skip-cli
```

This will:
- Ensure **ripgrep** and **tshark** are installed (unless `--skip-cli`)
- Copy skills into `~/.cline/skills/`
- Copy workflows into your global Cline workflows dir (and optional project dir)

### Option B — Manual install

**1. Install skills:**
```bash
# macOS / Linux
cp -r skills/android-log-analysis ~/.cline/skills/
cp -r skills/android-pcap-analysis ~/.cline/skills/

# Windows (PowerShell)
Copy-Item -Recurse skills\android-log-analysis $env:USERPROFILE\.cline\skills\
Copy-Item -Recurse skills\android-pcap-analysis $env:USERPROFILE\.cline\skills\
```

**2. Install workflows** (project-level, version controlled):
```bash
mkdir -p .clinerules/workflows
cp -r workflows/* .clinerules/workflows/
```

---

## Usage

In VS Code with Cline, type a workflow slash command:

```
/battery-troubleshooting.md
/emergency-call-troubleshooting.md
/ims-pcap-troubleshooting.md
```

Cline will ask for your log file/zip/folder path and run the analysis.

You can also invoke directly:
```
/battery-troubleshooting.md /path/to/logcat.txt
```

### Controlling output locations with WORKFLOW_OUTPUT_DIR

Workflow output paths are resolved in three layers:

1. **`WORKFLOW_OUTPUT_DIR` env var (highest priority)**  
2. **`output.default_base` in `workflow_config.yaml`**  
3. **Input file directory (fallback)**  

Each workflow still appends its own frontmatter `output.dir` on top of the
resolved base directory.

**Examples:**

- **With `WORKFLOW_OUTPUT_DIR` set:**

  ```bash
  export WORKFLOW_OUTPUT_DIR=~/analysis-outputs
  # Battery workflow will write under:
  #   ~/analysis-outputs/battery-analysis-output/...
  ```

- **With only `workflow_config.yaml` configured:**

  ```yaml
  # workflow_config.yaml
  output:
    default_base: ./workflow-output
  ```

  Battery workflow output goes under:

  ```text
  ./workflow-output/battery-analysis-output/...
  ```

If neither `WORKFLOW_OUTPUT_DIR` nor `output.default_base` is set, outputs are
written relative to the input file location (previous behavior).

---

## Structure

```
skills/
  android-log-analysis/       ← Cline skill for logcat files (uses rg)
    SKILL.md                  ← Skill instructions
    patterns/                 ← Shared reusable pattern templates
      wakelock.yaml
      power.yaml
      ims-sip.yaml
      ril.yaml
    scripts/                  ← Shared post-processing scripts
      tail_lines.py           ← Cross-platform tail -n
      decode_carriers.py      ← Carrier code → full name
      decode_timestamps.py    ← Normalize timestamps to ISO 8601

  android-pcap-analysis/      ← Cline skill for PCAP files (uses tshark)
    SKILL.md
    patterns/
      sip.yaml
      dns.yaml
      http.yaml
    scripts/
      tail_lines.py
      decode_sip.py           ← Format SIP flow as call flow table

workflows/
  battery-troubleshooting.md          ← Battery drain analysis
  emergency-call-troubleshooting.md   ← E911/SOS call failure analysis
  ims-pcap-troubleshooting.md         ← IMS/VoLTE PCAP analysis
  scripts/                            ← Workflow-specific scripts
    decode_wakelock.py                ← Pair acquire/release, flag leaks
    decode_ril.py                     ← Decode RIL/PDP numeric codes
```

---

## Input Types

All workflows accept:
- **Single file** — `logcat.txt`, `capture.pcap`
- **Folder** — files are matched by glob pattern per workflow config
- **Zip archive** — only matching files are extracted (cached next to zip)

---

## Extending

**Add a new workflow:**
1. Create `workflows/my-workflow.md` with YAML frontmatter defining `input`, `include`, `patterns`, and `final_summary_prompt`
2. Copy to `.clinerules/workflows/`
3. No changes to skills needed

**Add a new shared pattern template:**
1. Create `skills/android-log-analysis/patterns/my-pattern.yaml`
2. Copy to `~/.cline/skills/android-log-analysis/patterns/`
3. Reference it in any workflow with `include: [my-pattern]`

**Add a post-processing script:**
- Shared (reusable across workflows): add to `skills/<skill-name>/scripts/`
- Workflow-specific: add to `workflows/scripts/`
- Contract: stdin → stdout, accepts `--source-file <path>` (optional, for multi-pass)

---

## Workflow Config Reference

```yaml
---
workflow: my-workflow
description: What this workflow does

output:
  # `dir` is a relative subdirectory under WORKFLOW_OUTPUT_DIR (if set),
  # otherwise relative to the input file location.
  dir: ./output-dir
  filename: "out_{{timestamp}}.txt"

default_max_lines: 200           # max lines per pattern section

input:
  - path: "logcat*.txt"          # glob/regex to match files
    include: [wakelock, power]   # shared pattern templates
    templates:
      - id: my_pattern
        pattern: "regex here"
        context_lines: 5
        max_lines: 100           # overrides default_max_lines
        description: Human-readable description of what this captures.
        post_process: my_script.py    # optional
        summary_prompt: >             # optional — triggers LLM summary
          Analyze these entries and summarize findings.

final_summary_prompt: >          # optional — overall conclusion
  Provide a final diagnosis based on all findings above.
---

# Workflow Title

Steps for Cline to follow...
```
