---
name: android-pcap-analysis
description: >-
  Analyzes PCAP/PCAPNG network capture files using tshark. Given a pcap file,
  zip archive, or folder and a workflow pattern config, applies tshark display
  filters per pattern and writes a structured output file with descriptions,
  filtered packet fields, per-pattern LLM summaries, and a final summary.
  Use when asked to filter, analyze, or troubleshoot a PCAP or network capture file.
---

# Android PCAP Analysis Skill

## Prerequisites

Check that `tshark` is installed:

```
tshark --version
```

If missing, stop and print these install instructions:
- macOS: `brew install wireshark` (includes tshark)
- Linux (Debian/Ubuntu): `sudo apt install tshark`
- Linux (Fedora/RHEL): `sudo dnf install wireshark-cli`
- Windows: Download and install Wireshark from https://www.wireshark.org/download.html (includes tshark)

Also check Python 3 is available: `python3 --version`

---

## Step 1 — Resolve Input Files

Same input handling as android-log-analysis skill.

The workflow frontmatter has an `input` list. Each entry has:
- `path`: a glob/regex pattern to match filenames (e.g. `"*.pcap"`, `"capture*.pcapng"`)
- `include`: shared pattern template names to load
- `patterns`: inline pattern definitions

Detect what the user provided:

**Single file** — use directly.

**Folder** — list files, match each against `input[].path`. All matches run.

**Zip archive**:
1. List contents: `unzip -l <archive.zip>`
2. Match filenames against `input[].path`
3. Extract only matched files (skip if `<zip_dir>/<archive_name>_extracted/` exists):
   `unzip -j <archive.zip> "<matched_file>" -d <zip_dir>/<archive_name>_extracted/`

---

## Step 2 — Resolve Patterns Per Input Entry

For each `input[]` entry:
1. Load each name in `include` from `~/.cline/skills/android-pcap-analysis/patterns/<name>.yaml`
2. Merge with inline `patterns` from that input entry
3. Inline patterns take precedence on id clash

---

## Step 3 — Create Output File

Create output directory from `output.dir` (relative to the provided pcap path).
Filename: `output.filename` with `{{timestamp}}` replaced by `YYYYMMDD_HHMMSS`.

---

## Step 4 — For Each Input Entry × Each Matched File × Each Pattern

Write input group header:
```
=== INPUT: <input.path> ===
```

For each pattern, for each matched source file:

**4a. Build tshark command from pattern fields:**
```
tshark -r <file> -Y "<filter>" -T fields -e <field1> -e <field2> ... -E header=y -E separator="|"
```

**4b. Apply max_lines cap** (pattern `max_lines` → workflow `default_max_lines` → default 200):
```
tshark ... | python3 ~/.cline/skills/android-pcap-analysis/scripts/tail_lines.py --max-lines <M>
```

**4c. If `post_process` defined**, resolve script (check `<workflow_dir>/scripts/` first, then `~/.cline/skills/android-pcap-analysis/scripts/`):
```
tshark ... | python3 tail_lines.py --max-lines <M> | python3 <script> --source-file <file>
```

**4d. Write section to output file:**
```
---
PATTERN: <pattern.id>  |  SOURCE: <filename>  |  MATCHES: <N>(showing last <M> if capped)
<pattern.description>
---

<tshark output>

```

If no output (zero packets matched):
```
---
PATTERN: <pattern.id>  |  SOURCE: <filename>  |  MATCHES: 0
---

[No packets matched]

```

**4e. If pattern has `summary_prompt`:**
Read the filtered output just written. Generate LLM summary using `summary_prompt`. Append:
```
SUMMARY:
<generated summary>

```

---

## Step 5 — Final Summary

After all patterns for all inputs are written, if `final_summary_prompt` defined:

Read the entire output file. Generate final summary using `final_summary_prompt`. Append:
```
---
FINAL SUMMARY
---
<generated final summary>
```

---

## Step 6 — Report

Tell the user the output file path and a one-line summary (e.g. "Found 23 SIP transactions, 4 SIP errors. Output saved to ./ims-analysis-output/ims_20240115_103045.txt").
