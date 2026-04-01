---
name: log-template-creator
description: >-
  Guides a developer through creating a reusable log template YAML for the
  android-log-analysis skill. Asks for ripgrep regex patterns, tests them
  against a sample log file if available, and writes the template to
  templates/log/. Use this before workflow-creator when you need new patterns.
---

# Log Template Creator Skill

## What This Skill Does

Helps a developer author a new log template YAML file. Log templates define
ripgrep regex patterns used by `android-log-analysis` to filter Android log
files (logcat, bugreport, etc.). The resulting YAML can be included in any
workflow via `include:` in the workflow frontmatter.

---

## Step 1 — Understand the Goal

Ask the developer:
- What log files will this template target? (e.g. logcat, bugreport, kernel log)
- What behavior or issue are they trying to detect?
- Do they have a sample log file to test patterns against?

---

## Step 2 — Gather Template Metadata

Ask for:
- **Template ID** — a short slug with no spaces (e.g. `bluetooth`, `wifi-scan`). This becomes the filename.
- **Description** — one sentence describing what this template covers.

---

## Step 3 — Define Patterns

For each pattern the developer wants to add, gather:
- **Pattern ID** — short slug for this specific pattern (e.g. `bt_connect`, `bt_error`)
- **Regex** — ripgrep-compatible regular expression. Remind the developer:
  - Use `|` for alternation: `connect|disconnect`
  - Case-insensitive matching is on by default
  - Test with `rg "<pattern>" <log_file>` if unsure
- **Context lines** — lines before/after each match to include (default: 3)
- **Description** — what this pattern captures and why it matters
- **Summary prompt** (optional) — an AI analysis prompt that describes what to look for in the matches, e.g. "Identify failed connection attempts and their error codes."
- **Post-process script** (optional) — only needed if matches require custom decoding. Leave blank unless the developer has a specific script in mind.

Ask: "Do you want to add another pattern?" Repeat until done.

---

## Step 4 — Test Patterns (if sample file provided)

If the developer provided a sample log file, test each pattern by invoking the
`android-log-analysis` skill with the pattern and file. Show the match count
and a preview of the first few matches. If a pattern returns zero matches,
suggest refining it.

---

## Step 5 — Write the Template YAML

Write the template to `templates/log/<id>.yaml` using this structure:

```yaml
id: <id>
description: <description>

templates:
  - id: <pattern_id>
    pattern: "<regex>"
    context_lines: <n>
    description: >
      <description>
    summary_prompt: >
      <summary_prompt>
```

Omit `summary_prompt` if none was provided. Omit `post_process` unless specified.
Add additional pattern entries under `templates:` for each pattern gathered.

---

## Step 6 — Confirm and Show Next Steps

Show the developer the written file path. Then tell them:

> To use this template in a workflow, add the following to the workflow's
> `input` entry:
> ```yaml
> include:
>   - ../templates/log/<id>.yaml
> ```
> Run `workflow-creator` to build a new workflow, or add it to an existing one.
