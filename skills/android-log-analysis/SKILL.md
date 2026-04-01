---
name: android-log-analysis
description: >-
  Analyzes Android logcat files using ripgrep. Given a log file, zip archive,
  or folder and a workflow pattern config, filters log lines per pattern and
  writes a structured output file with descriptions, filtered sections,
  per-pattern LLM summaries, and a final summary. Use when asked to filter,
  analyze, or troubleshoot an Android log file.
---

# Android Log Analysis Skill

## Prerequisites

Check that `rg` (ripgrep) is installed:

```
rg --version
```

If missing, stop and print these install instructions:
- macOS: `brew install ripgrep`
- Linux (Debian/Ubuntu): `sudo apt install ripgrep`
- Linux (Fedora/RHEL): `sudo dnf install ripgrep`
- Windows: `winget install BurntSushi.ripgrep.MSVC`

Also check Python 3 is available: `python3 --version`

---

## Step 1 — Resolve Input Files

The workflow frontmatter has an `input` list. Each entry has:
- `path`: a glob/regex pattern to match filenames
- `include`: shared pattern template names to load
- `patterns`: inline pattern definitions

Detect what the user provided:

**Single file** — use it directly, match against each `input[].path`.

**Folder** — list files, match each against `input[].path` globs. All matches run.

**Zip archive** — do:
1. List zip contents: `unzip -l <archive.zip>`
2. Match filenames against each `input[].path`
3. Extract only matched files (skip if `<zip_dir>/<archive_name>_extracted/` already exists):
   `unzip -j <archive.zip> "<matched_file>" -d <zip_dir>/<archive_name>_extracted/`
4. Use extracted files as input

---

## Step 2 — Resolve Patterns Per Input Entry

For each `input[]` entry:
1. Load each name in `include` from `~/.cline/skills/android-log-analysis/patterns/<name>.yaml`
2. Merge with inline `patterns` defined in that input entry
3. Final pattern list = included patterns + inline patterns (inline takes precedence on id clash)

---

## Step 3 — Create Output File

Create the output directory from `output.dir` (relative to the provided log path).
Output filename: `output.filename` with `{{timestamp}}` replaced by current datetime (`YYYYMMDD_HHMMSS`).

---

## Step 4 — For Each Input Entry × Each Matched File × Each Pattern

Write input group header to output file:
```
=== INPUT: <input.path> ===
```

For each pattern in this input entry, for each matched source file:

**4a. Run rg:**
```
rg --context <context_lines> --line-number --no-heading "<pattern>" <file>
```

**4b. Apply max_lines cap** (most specific wins: pattern `max_lines` → workflow `default_max_lines` → default 200):
```
rg ... | python3 ~/.cline/skills/android-log-analysis/scripts/tail_lines.py --max-lines <M>
```

**4c. If `post_process` defined**, resolve script path (check `<workflow_dir>/scripts/` first, then `~/.cline/skills/android-log-analysis/scripts/`), then pipe:
```
rg ... | python3 tail_lines.py --max-lines <M> | python3 <script> --source-file <file>
```

**4d. Write section to output file:**
```
---
PATTERN: <pattern.id>  |  SOURCE: <filename>  |  MATCHES: <N>(showing last <M> if capped)
<pattern.description>
---

<filtered output lines>

```

If no matches:
```
---
PATTERN: <pattern.id>  |  SOURCE: <filename>  |  MATCHES: 0
---

[No matches found]

```

**4e. If pattern has `summary_prompt`:**
Read the filtered lines just written for this pattern+source. Generate a concise LLM summary using the `summary_prompt` as instruction. Append to output file:
```
SUMMARY:
<generated summary>

```

---

## Step 5 — Final Summary

After all patterns for all input entries are written, if `final_summary_prompt` is defined in the workflow frontmatter:

Read the entire output file. Generate a final summary using `final_summary_prompt` as instruction. Append:
```
---
FINAL SUMMARY
---
<generated final summary>
```

---

## Step 6 — Report

Tell the user the output file path and a one-line summary of what was found (e.g. "Found 47 wakelock matches, 0 drain anomalies. Output saved to ./battery-analysis-output/battery_20240115_103045.txt").
