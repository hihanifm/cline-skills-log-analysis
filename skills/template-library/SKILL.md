---
name: template-library
description: >-
  Browse and discover available filter templates. Lists all templates from
  project-local and shared default locations, with their IDs, descriptions,
  and pattern summaries. Use when you want to know what templates exist before
  building or updating a workflow.
---

# Template Library Skill

## What This Skill Does

Searches all known template locations and presents a catalogue of available
filter templates — both project-local and shared defaults. Helps the user
discover what's available before creating a workflow or adding an `include:`.

---

## Step 1 — Locate Templates

Search the following directories in order. Read every `.yaml` file found.

**Project-local (check first):**
- `log-templates/log/` — relative to the current working directory
- `log-templates/pcap/` — relative to the current working directory

**Shared defaults (deployed):**
- `~/.cline/skills/template-engine/templates/log/`
- `~/.cline/skills/template-engine/templates/pcap/`

For each YAML file found, read its contents and extract:
- `templates[*].id` — the template ID (used in `include:`)
- `templates[*].description` — what the template captures
- `templates[*].pattern` or `templates[*].filter` — the filter expression
- Number of pattern entries in the file

---

## Step 2 — Present the Catalogue

Group results by location (project-local vs shared) and by type (log vs pcap).

Format as a table or list, for example:

```
## Shared — Log Templates

| ID            | Description                              | Patterns |
|---------------|------------------------------------------|----------|
| wakelock      | WakeLock acquire/release events          | 2        |
| power         | Power manager state transitions          | 3        |
| ims-sip       | IMS SIP signaling messages               | 2        |
| ril           | RIL/modem request and response logs      | 4        |

## Shared — PCAP Templates

| ID   | Description                              | Patterns |
|------|------------------------------------------|----------|
| sip  | SIP signaling — REGISTER, INVITE, BYE   | 3        |
| dns  | DNS queries and responses                | 1        |
| http | HTTP requests and responses              | 2        |
```

If project-local templates exist, list them first under **Project-local**.

---

## Step 3 — Offer Next Steps

After presenting the catalogue, ask the user what they'd like to do:

- **Use a template** → tell them to add it to a workflow `include:` using its short path (e.g. `log/wakelock.yaml`)
- **Create a new template** → direct them to run `log-template-creator` or `pcap-template-creator`
- **See pattern details** → read the full YAML for any template and show the filter expressions and field lists
