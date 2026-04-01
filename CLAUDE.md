# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Android log and PCAP network capture analysis system for Cline (VS Code AI assistant). Uses a two-stage pipeline:
1. **Deterministic context builder** — ripgrep/tshark filters log/PCAP files into a structured `context.yaml`
2. **LLM synthesizer** — reads `context.yaml` and produces a human-readable markdown report

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
# Step 1: Build context (prints context.yaml path to stdout)
python3 skills/workflow-orchestrator/scripts/context_builder_agent.py \
  --workflow skills/workflow-creator/examples/battery-troubleshooting.md \
  --input /path/to/logcat.txt

# Step 2: Synthesize report (prints report.md path to stdout)
python3 skills/workflow-orchestrator/scripts/log_synthesizer_agent.py \
  --context /path/to/context.yaml
```

Progress messages go to stderr; the output file path goes to stdout (for Cline to capture).

## Configuration

**`workflow_config.yaml`** (repo root) — central config for LLM backend and output directories. Loaded by `config.py`, which caches and merges it with built-in defaults.

Key settings:
- `llm.backend`: `cline` (default, writes `<!-- SUMMARY_PROMPT -->` markers) or `anthropic` (calls API directly). Override at runtime with the `LLM_BACKEND` env var.
- `llm.api_key_env`: env var name for the Anthropic API key (default: `ANTHROPIC_API_KEY`)
- `output.base_dir_env`: env var that overrides the output base dir (default: `WORKFLOW_OUTPUT_DIR`)
- `output.default_base`: fallback base dir when env var is not set (default: `./workflow-output`)

Output dir resolution order: `WORKFLOW_OUTPUT_DIR` env var → `workflow_config.yaml` `default_base` → input file directory. Individual workflows always append their own `output.dir` subdirectory on top.

## Architecture

### Shared Python modules (repo root)
- **`yaml_utils.py`** — PyYAML wrapper: `load_yaml()`, `load_yaml_frontmatter()`, `write_yaml()`. All callers use this instead of importing PyYAML directly.
- **`config.py`** — Loads `workflow_config.yaml`; exposes `get_llm_config()`, `get_output_config()`, `resolve_output_base()`.
- **`workflow_paths.py`** — Output path helpers: `resolve_output_dir()` (env+config-aware), `ensure_output_dir()`.

### Skills (`skills/`)
Each skill has a `SKILL.md` (instructions for Cline) and a `scripts/` directory. Four skills:
- **`android-log-analysis`** — `log_filter.py` wraps ripgrep; returns `FilterResult` dataclass. Context-aware capping never orphans match context blocks.
- **`android-pcap-analysis`** — `pcap_filter.py` wraps tshark with field extraction; simple line capping.
- **`workflow-orchestrator`** — Cline-facing skill that orchestrates the two-script pipeline end-to-end. Contains `context_builder_agent.py` and `log_synthesizer_agent.py` in its `scripts/` directory.
- **`template-engine`** — `template_runner.py` loads a template YAML, resolves `include:` paths + inline templates, auto-detects skill type (PCAP if template has both `filter` and `fields`; log otherwise), runs patterns.

### Templates (`skills/template-engine/templates/`)
Reusable YAML filter definitions packaged inside the `template-engine` skill. Deployed to `~/.cline/skills/template-engine/templates/` automatically by `setup.py`. Workflows reference them with short paths (`log/wakelock.yaml`) resolved by `template_runner.load_template()` against the deployed skill dir.

### Workflows (`skills/workflow-creator/examples/`)
Example workflow `.md` files with YAML frontmatter. Serve as both reference implementations for the `workflow-creator` skill and the actual workflows deployed to `~/Documents/Cline/Workflows/` by `setup.py`. The frontmatter defines `input` globs, which templates to `include`, any inline `templates`, `output` path config, and `final_summary_prompt`.

### Post-processors (`skills/postprocessors/scripts/`)
All decode/format scripts read from stdin and write to stdout, and optionally accept `--source-file <path>` for multi-pass use. Packaged in the `postprocessors` skill and deployed to `~/.cline/skills/postprocessors/scripts/`. Referenced by filename only in template pattern definitions via `post_process:`.

## Extending

**New workflow:** Create `.clinerules/workflows/<name>.md` in the project repo. Invoke `workflow-creator` skill to be guided through it.

**New template:** Create `templates/log/<name>.yaml` or `templates/pcap/<name>.yaml` in the project repo. Invoke `log-template-creator` or `pcap-template-creator` skill. Reference with short path `log/<name>.yaml` in workflow `include:`.

**New post-processor:** Create `postprocessors/<name>.py` in the project repo. Invoke `postprocessors` skill for guidance. Reference with `post_process: <name>.py` in a template pattern.

Project-local assets (`templates/`, `postprocessors/`, `.clinerules/workflows/`) take priority over the shared skill defaults and can be committed to the project repo for team sharing.
