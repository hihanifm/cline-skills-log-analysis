# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Android log and PCAP network capture analysis system for Cline (VS Code AI assistant). Uses a two-stage pipeline:
1. **Deterministic context builder** — ripgrep/tshark filters log/PCAP files into a structured `context.txt`
2. **LLM synthesizer** — reads `context.txt` and produces a human-readable markdown report

## Setup & Installation

```bash
# Full install (ripgrep + tshark + deploy skills + deploy workflows)
./setup.py

# Skip CLI tool installation (rg/tshark already installed)
./setup.py --skip-cli

# Also deploy workflows to a specific project directory
./setup.py --project-dir /path/to/project
```

Skills are deployed to `~/.cline/skills/`, workflows to `~/Documents/Cline/Workflows/`.

One Python dependency: `PyYAML` (used by `yaml_utils.py`). All other scripts use stdlib only.

## Running the Pipeline Manually

```bash
# Step 1: Build context → out/battery-troubleshooting/context.txt
python3 skills/workflow-orchestrator/scripts/context_builder_agent.py \
  --workflow skills/workflow-creator/examples/battery-troubleshooting.md \
  --input /path/to/logcat.txt

# Step 2: Synthesize report → out/battery-troubleshooting/report.md
python3 skills/workflow-orchestrator/scripts/log_synthesizer_agent.py \
  --context out/battery-troubleshooting/context.txt
```

Progress messages go to stderr; the output file path goes to stdout (for Cline to capture).

## Configuration

**`workflow_config.yaml`** (repo root) — central config for LLM backend and output directories. Loaded by `config.py`, which caches and merges it with built-in defaults.

Key settings:
- `llm.backend`: `cline` (default, writes `<!-- SUMMARY_PROMPT -->` markers) or `openai` (calls OpenAI-compatible API directly). Override at runtime with the `LLM_BACKEND` env var.
- `llm.base_url`: base URL for the OpenAI-compatible API (default: `https://api.openai.com/v1`). Works with OpenAI, Azure, Ollama, LM Studio, etc.
- `llm.model`: model name to use when backend is `openai` (default: `gpt-4o-mini`)
- API key: set the `LLM_API_KEY` environment variable — never stored in config files

Output is written to `out/<workflow-name>/` relative to the working directory. If that directory already exists, a new one is created (`out/<workflow-name>-2/`, `-3/`, etc.) so previous runs are preserved:
- `out/<workflow-name>/context.txt` — structured filter context
- `out/<workflow-name>/report.md` — full report with filtered log lines + summaries
- `out/<workflow-name>/summary.md` — final summary only (no log lines)
- `out/<workflow-name>/errors.txt` — warnings and errors (only written if issues occurred)

## Architecture

### Shared Python modules (repo root)
- **`yaml_utils.py`** — PyYAML wrapper: `load_yaml()`, `load_yaml_frontmatter()`, `write_yaml()`. All callers use this instead of importing PyYAML directly.
- **`config.py`** — Loads `workflow_config.yaml`; exposes `get_llm_config()` and `get_output_config()`.

### Skills (`skills/`)
Each skill has a `SKILL.md` (instructions for Cline) and an optional `scripts/` directory. Nine skills:
- **`android-log-analysis`** — `log_filter.py` wraps ripgrep; returns `FilterResult` dataclass. `tail_lines.py` handles context-aware capping that never orphans match context blocks.
- **`android-pcap-analysis`** — `pcap_filter.py` wraps tshark with field extraction; `tail_lines.py` handles simple line capping.
- **`workflow-orchestrator`** — Cline-facing skill that orchestrates the two-script pipeline end-to-end. Contains `context_builder_agent.py` and `log_synthesizer_agent.py` in its `scripts/` directory.
- **`template-engine`** — `template_runner.py` loads a template YAML, resolves `include:` paths + inline templates, auto-detects skill type (PCAP if template has both `filter` and `fields`; log otherwise), runs patterns.
- **`template-library`** — Centralised reusable YAML templates (4 log, 3 pcap). Deployed to `~/.cline/skills/template-library/templates/`. No scripts directory.
- **`postprocessors`** — 5 decode/format scripts: `decode_wakelock.py`, `decode_ril.py`, `decode_carriers.py`, `decode_timestamps.py`, `decode_sip.py`. All read stdin → stdout.
- **`log-template-creator`** — Instructions-only skill. Guides authoring new log templates using `android-log-analysis` for pattern testing.
- **`pcap-template-creator`** — Instructions-only skill. Guides authoring new PCAP templates using `android-pcap-analysis` for filter testing.
- **`workflow-creator`** — Instructions-only skill + 3 example workflows in `examples/`. Guides end-to-end workflow authoring.

### Templates (`skills/template-library/templates/`)
Reusable YAML filter definitions packaged in the `template-library` skill. Deployed to `~/.cline/skills/template-library/templates/` automatically by `setup.py`. Workflows reference them with short paths (`log/wakelock.yaml`) resolved by `template_runner.load_template()` against the deployed skill dir.

Available templates:
- **Log:** `log/wakelock.yaml`, `log/power.yaml`, `log/ril.yaml`, `log/ims-sip.yaml`
- **PCAP:** `pcap/sip.yaml`, `pcap/dns.yaml`, `pcap/http.yaml`

### Workflows (`skills/workflow-creator/examples/`)
Example workflow `.md` files with YAML frontmatter. Serve as both reference implementations for the `workflow-creator` skill and the actual workflows deployed to `~/Documents/Cline/Workflows/` by `setup.py`. The frontmatter defines `input` globs, which templates to `include`, any inline `templates`, and `final_summary_prompt`.

### Post-processors (`skills/postprocessors/scripts/`)
All decode/format scripts read from stdin and write to stdout, and optionally accept `--source-file <path>` for multi-pass use. Packaged in the `postprocessors` skill and deployed to `~/.cline/skills/postprocessors/scripts/`. Referenced by filename only in template pattern definitions via `post_process:`.

## Extending

**New workflow:** Create `.clinerules/workflows/<name>.md` in the project repo. Invoke `workflow-creator` skill to be guided through it.

**New log template:** Create `log-templates/log/<name>.yaml` in the project repo. Invoke `log-template-creator` skill to be guided through authoring and testing it. Reference with short path `log/<name>.yaml` in workflow `include:`.

**New PCAP template:** Create `log-templates/pcap/<name>.yaml` in the project repo. Invoke `pcap-template-creator` skill to be guided through authoring and testing it. Reference with short path `pcap/<name>.yaml` in workflow `include:`.

**New post-processor:** Create `log-postprocessors/<name>.py` in the project repo. Invoke `postprocessors` skill for guidance. Reference with `post_process: <name>.py` in a template pattern.

Project-local assets (`log-templates/`, `log-postprocessors/`, `.clinerules/workflows/`) take priority over the shared skill defaults and can be committed to the project repo for team sharing.
