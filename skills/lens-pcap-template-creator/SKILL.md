---
name: lens-pcap-template-creator
description: >-
  Guides a developer through creating a reusable PCAP template YAML for the
  lens-pcap-filter skill. Asks for tshark display filters and field lists,
  tests them against a sample PCAP if available, and writes the template to
  log-templates/pcap/. Use this before lens-workflow-creator when you need new PCAP patterns.
---

# PCAP Template Creator Skill

## What This Skill Does

Helps a developer author a new PCAP template YAML file. PCAP templates define
tshark display filters and field extraction lists used by `lens-pcap-filter`
to analyze `.pcap` / `.pcapng` capture files. The resulting YAML can be included
in any workflow via `include:` in the workflow frontmatter.

---

## Step 1 — Understand the Goal

Ask the developer:
- What protocol or network behavior are they analyzing? (e.g. SIP/VoLTE, DNS, HTTP, RTP)
- What specific events or errors are they looking for?
- Do they have a sample PCAP file to test filters against?

---

## Step 2 — Gather Template Metadata

Ask for:
- **Template ID** — a short slug with no spaces (e.g. `rtp`, `dhcp`). This becomes the filename.
- **Description** — one sentence describing what this template covers.

---

## Step 3 — Define Patterns

For each pattern the developer wants to add, gather:

- **Pattern ID** — short slug for this specific pattern (e.g. `rtp_loss`, `dhcp_request`)
- **tshark display filter** — a valid tshark display filter expression. Remind the developer:
  - Test with `tshark -r <file> -Y "<filter>"` if unsure
  - Examples: `rtp`, `dhcp`, `dns.flags.rcode != 0`, `sip.Method == "INVITE"`
- **Fields to extract** — list of tshark field names. Always include `frame.number` and
  `frame.time_relative` as the first two. Then add protocol-specific fields.

  Common field references by protocol:
  | Protocol | Useful fields |
  |----------|---------------|
  | SIP      | `sip.Method`, `sip.Status-Code`, `sip.Status-Phrase`, `ip.src`, `ip.dst`, `sip.r-uri`, `sip.CSeq` |
  | DNS      | `dns.qry.name`, `dns.qry.type`, `dns.flags.rcode`, `ip.src`, `ip.dst` |
  | RTP      | `rtp.ssrc`, `rtp.seq`, `rtp.timestamp`, `rtp.payload_type`, `ip.src`, `ip.dst` |
  | HTTP     | `http.request.method`, `http.request.uri`, `http.response.code`, `ip.src`, `ip.dst` |
  | DHCP     | `dhcp.type`, `dhcp.hw.mac_addr`, `dhcp.ip.your`, `dhcp.option.hostname` |
  | TCP      | `tcp.flags`, `tcp.srcport`, `tcp.dstport`, `ip.src`, `ip.dst` |

- **Description** — what this filter captures and why it matters
- **Summary prompt** (optional) — AI analysis prompt describing what to look for in the output
- **Post-process script** (optional) — available scripts live in `skills/lens-postprocessors/scripts/` (e.g. `decode_sip.py`). Leave blank if none apply.

Ask: "Do you want to add another pattern?" Repeat until done.

---

## Step 4 — Test Patterns (if sample file provided)

If the developer provided a sample PCAP file, test each pattern by invoking the
`lens-pcap-filter` skill with the filter, fields, and file. Show the packet
count and a preview of the first few rows. If a filter returns zero packets, suggest
refining the display filter.

---

## Step 5 — Write the Template YAML

Write the template to `log-templates/pcap/<id>.yaml` in the project repo root using this structure:

```yaml
id: <id>
description: <description>

templates:
  - id: <pattern_id>
    filter: "<tshark_display_filter>"
    fields:
      - frame.number
      - frame.time_relative
      - <field_1>
      - <field_2>
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

> Template written to `log-templates/pcap/<id>.yaml` in your project repo.
> Commit this file so colleagues can use it too.
>
> To use it in a workflow, add to the `input` entry:
> ```yaml
> include:
>   - pcap/<id>.yaml
> ```
> Run `lens-workflow-creator` to build a new workflow, or add it to an existing one.
