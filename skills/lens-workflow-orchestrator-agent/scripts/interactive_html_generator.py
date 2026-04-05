"""
interactive_html_generator.py — Build a self-contained interactive HTML report.

Reads report.md (produced by log_synthesizer_agent.py) and emits
report_interactive.html alongside it, containing:
  - Multi-lane SVG timeline — one lane per template/pattern
  - Filterable event cards grouped by pattern
  - Color-coded by Android log severity (V/D/I/W/E/F)
  - Pure vanilla JS, no external dependencies, no LLM required

Usage:
    python3 interactive_html_generator.py --report /path/to/out/<name>/report.md

Prints the HTML path to stdout. Progress goes to stderr.
Can also be imported and called via render(report_path).
"""

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class LogEvent:
    raw: str
    timestamp_str: Optional[str]
    ts_minutes: Optional[float]
    log_level: str
    severity: str
    tag: str
    message: str
    pattern_id: str
    event_id: int = 0


@dataclass
class PatternSection:
    pattern_id: str
    description: str
    source_file: str
    match_count: int
    input_glob: str
    events: List[LogEvent] = field(default_factory=list)


# ── Constants ─────────────────────────────────────────────────────────────────

# Android logcat: optional line-number prefix (e.g. "187639:"), then
# MM-DD HH:MM:SS.mmm, one or more PID/TID/UID numbers, LEVEL, TAG: msg.
# Tag may contain brackets: SIPMSG[0,2].
_LOGCAT_RE = re.compile(
    r'^(?:\d+:)?(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(?:\d+\s+)+([VDIWEF])\s+([\w./:\[\],-]+):\s*(.*)'
)
# Simpler fallback: optional line-number prefix + timestamp at start of line
_TS_ONLY_RE = re.compile(
    r'^(?:\d+:)?(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(.*)'
)
# report.md section header line
_SECTION_HDR_RE = re.compile(
    r'\*\*PATTERN:\*\*\s+(\S+)\s+\|\s+\*\*SOURCE:\*\*\s+(\S+)\s+\|\s+\*\*MATCHES:\*\*\s+(\d+)'
)
# ## INPUT: <glob>
_GLOB_HDR_RE = re.compile(r'^##\s+INPUT:\s+(.+)$')
# *italic description* (single line)
_DESC_RE = re.compile(r'^\*([^*]+)\*$')

_LEVEL_SEVERITY: Dict[str, str] = {
    "V": "info", "D": "info", "I": "info",
    "W": "warning", "E": "error", "F": "critical",
}

# Per-pattern lane colors (warm orange/amber palette, cycling)
_PATTERN_COLORS = [
    "#e87830",  # primary orange
    "#e8b840",  # amber
    "#c85a20",  # dark orange
    "#a06020",  # brown-orange
    "#f0a050",  # light orange
    "#d04010",  # red-orange
    "#b8880a",  # dark amber
    "#e8d040",  # yellow
]

# Severity dot fill colors
_SEVERITY_COLOR: Dict[str, str] = {
    "critical": "#e83020",
    "error":    "#e85030",
    "warning":  "#e8b840",
    "info":     "#8ec07c",
}


# ── Embedded CSS ──────────────────────────────────────────────────────────────

_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: #0f1117;
  color: #e8eaf0;
  font-size: 14px;
  line-height: 1.6;
}

#app {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1.5rem 2rem 4rem;
}

/* ── Header ───────────────────────────────────────────────────────────────── */
#hdr {
  padding: 1.5rem 0 1rem;
  border-bottom: 1px solid #2a2d3a;
  margin-bottom: 1.25rem;
}

#hdr h1 {
  font-size: 1.5rem;
  font-weight: 700;
  color: #fff;
  margin-bottom: 0.4rem;
}

.meta {
  font-size: 13px;
  color: #8899aa;
  margin-bottom: 0.3rem;
}

.meta code {
  background: #1a1d27;
  border: 1px solid #2a2d3a;
  border-radius: 3px;
  padding: 0.1em 0.4em;
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 0.9em;
  color: #e8b86d;
}

.stats {
  font-size: 13px;
  color: #e87830;
  font-weight: 500;
}

h2 {
  font-size: 1rem;
  font-weight: 600;
  color: #c8cfe8;
  margin: 0 0 0.75rem;
}

/* ── Controls ─────────────────────────────────────────────────────────────── */
#controls {
  background: #131620;
  border: 1px solid #2a2d3a;
  border-radius: 8px;
  padding: 0.85rem 1rem;
  margin-bottom: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.ctrl-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.ctrl-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #5a6070;
  min-width: 58px;
}

.pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.pill {
  font-size: 11.5px;
  padding: 0.2em 0.75em;
  border-radius: 999px;
  border: 1.5px solid var(--c, #e87830);
  background: transparent;
  color: #5a6070;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  font-family: inherit;
}

.pill.active {
  background: color-mix(in srgb, var(--c, #e87830) 18%, transparent);
  color: var(--c, #e87830);
}

.pill:hover {
  background: color-mix(in srgb, var(--c, #e87830) 28%, transparent);
  color: var(--c, #e87830);
}

.sev-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
}

.sev-checks label {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 12.5px;
  color: #c8cfe8;
  cursor: pointer;
}

.sev-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ── Timeline ─────────────────────────────────────────────────────────────── */
#timeline-section {
  background: #0a0c12;
  border: 1px solid #2a2d3a;
  border-radius: 8px;
  padding: 1rem 1rem 0.5rem;
  margin-bottom: 1.25rem;
  overflow: hidden;
}

#timeline-wrap {
  overflow-x: auto;
  border-radius: 4px;
}

.lane-label {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 11px;
}

.ts-label {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 10px;
  fill: #4a5060;
}

.evt-dot {
  cursor: pointer;
  transition: opacity 0.15s;
}

.evt-dot:hover {
  filter: brightness(1.4);
}

.no-ts-note {
  color: #5a6070;
  font-size: 13px;
  font-style: italic;
  padding: 0.5rem 0;
}

/* ── Events section ───────────────────────────────────────────────────────── */
#visible-count {
  font-size: 13px;
  font-weight: 400;
  color: #5a6070;
}

.pattern-group {
  background: #131620;
  border: 1px solid #2a2d3a;
  border-radius: 8px;
  margin-bottom: 0.6rem;
  overflow: hidden;
}

.group-hdr {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 0.6rem 0.9rem;
  cursor: pointer;
  user-select: none;
}

.group-hdr:hover {
  background: #1a1d27;
}

.group-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.group-title {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 12.5px;
  font-weight: 600;
  color: #e8eaf0;
  flex-shrink: 0;
}

.group-desc {
  font-size: 12px;
  color: #6a7890;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.group-count {
  font-size: 11px;
  color: #4a5060;
  flex-shrink: 0;
}

.chevron {
  color: #4a5060;
  font-size: 13px;
  flex-shrink: 0;
}

.group-body {
  border-top: 1px solid #2a2d3a;
}

/* ── Event cards ──────────────────────────────────────────────────────────── */
.event-card {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.3rem 0.9rem;
  font-size: 12px;
  border-bottom: 1px solid #1a1d27;
  transition: background 0.1s;
  min-width: 0;
}

.event-card:last-child {
  border-bottom: none;
}

.event-card:hover {
  background: #1a1d27;
}

.event-card.highlighted {
  background: rgba(232,120,48,0.10);
  outline: 1px solid rgba(232,120,48,0.5);
  outline-offset: -1px;
}

.lv-badge {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  padding: 0.1em 0.45em;
  border-radius: 3px;
  border: 1px solid;
  flex-shrink: 0;
  line-height: 1.6;
}

.ev-tag {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 11px;
  color: #7a8898;
  flex-shrink: 0;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ev-ts {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 11px;
  color: #506070;
  flex-shrink: 0;
  white-space: nowrap;
}

.ev-msg {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 11.5px;
  color: #b8c0d0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
""".strip()


# ── Parser ────────────────────────────────────────────────────────────────────

def _parse_report(md_text: str) -> List[PatternSection]:
    """Parse report.md into a list of PatternSection objects with events."""
    sections: List[PatternSection] = []
    current: Optional[PatternSection] = None
    current_glob = ""
    in_code_block = False
    in_html_comment = False
    expect_desc = False

    for raw_line in md_text.splitlines():
        # Skip Cline placeholder HTML comments
        if in_html_comment:
            if "-->" in raw_line:
                in_html_comment = False
            continue
        if raw_line.startswith("<!--"):
            if "-->" not in raw_line:
                in_html_comment = True
            continue

        # Track current input glob group
        m_glob = _GLOB_HDR_RE.match(raw_line)
        if m_glob:
            current_glob = m_glob.group(1).strip()
            continue

        # Detect pattern section header
        m_hdr = _SECTION_HDR_RE.search(raw_line)
        if m_hdr:
            if current is not None:
                sections.append(current)
            current = PatternSection(
                pattern_id=m_hdr.group(1),
                description="",
                source_file=m_hdr.group(2),
                match_count=int(m_hdr.group(3)),
                input_glob=current_glob,
            )
            in_code_block = False
            expect_desc = True
            continue

        if current is None:
            continue

        # Capture description from the italic line right after the header
        if expect_desc and not in_code_block:
            stripped = raw_line.strip()
            if stripped in ("", "---"):
                pass  # keep waiting
            else:
                m_desc = _DESC_RE.match(stripped)
                if m_desc:
                    current.description = m_desc.group(1)
                expect_desc = False
            continue

        # Code block toggle
        if raw_line.strip() == "```":
            in_code_block = not in_code_block
            continue

        if not in_code_block:
            continue

        # Inside a code block — try to parse log lines
        line = raw_line.rstrip()
        if not line:
            continue

        m_logcat = _LOGCAT_RE.match(line)
        if m_logcat:
            ts_str: Optional[str] = m_logcat.group(1)
            level = m_logcat.group(2)
            tag = m_logcat.group(3).rstrip(":")
            msg = m_logcat.group(4)
        else:
            m_ts = _TS_ONLY_RE.match(line)
            if m_ts:
                ts_str = m_ts.group(1)
                level = ""
                tag = ""
                msg = m_ts.group(2)
            else:
                ts_str = None
                level = ""
                tag = ""
                msg = line

        evt = LogEvent(
            raw=line,
            timestamp_str=ts_str,
            ts_minutes=None,
            log_level=level,
            severity=_LEVEL_SEVERITY.get(level, "info"),
            tag=tag,
            message=msg,
            pattern_id=current.pattern_id,
        )
        current.events.append(evt)

    if current is not None:
        sections.append(current)

    return sections


def _normalize_timestamps(sections: List[PatternSection]) -> None:
    """Convert timestamp strings to relative float minutes (in-place)."""
    def _to_minutes(ts_str: str) -> Optional[float]:
        # Format: MM-DD HH:MM:SS.mmm
        try:
            date_part, time_part = ts_str.split()
            month, day = (int(x) for x in date_part.split("-"))
            h, m, s_ms = time_part.split(":")
            s, ms = s_ms.split(".")
            return (month * 44640 + day * 1440
                    + int(h) * 60 + int(m)
                    + int(s) / 60.0 + int(ms) / 60000.0)
        except Exception:
            return None

    all_ts: List[float] = []
    for section in sections:
        for evt in section.events:
            if evt.timestamp_str:
                t = _to_minutes(evt.timestamp_str)
                if t is not None:
                    evt.ts_minutes = t
                    all_ts.append(t)

    if not all_ts:
        return

    ts_min = min(all_ts)
    for section in sections:
        for evt in section.events:
            if evt.ts_minutes is not None:
                evt.ts_minutes -= ts_min


def _assign_event_ids(sections: List[PatternSection]) -> int:
    """Assign sequential event IDs. Returns total event count."""
    counter = 0
    for section in sections:
        for evt in section.events:
            evt.event_id = counter
            counter += 1
    return counter


# ── Timeline SVG builder ──────────────────────────────────────────────────────

def _build_timeline_svg(sections: List[PatternSection],
                        pattern_colors: Dict[str, str],
                        ts_max_minutes: float) -> str:
    """Build a multi-lane SVG timeline. Returns the SVG markup string."""
    LABEL_W = 158
    LEFT = 165
    RIGHT = 1185
    TW = RIGHT - LEFT
    LANE_H = 44
    N_LANES = len(sections)
    AXIS_Y = N_LANES * LANE_H + 8
    SVG_H = AXIS_Y + 28
    TS_RANGE = max(ts_max_minutes, 0.001)

    parts = [
        f'<svg id="timeline-svg" viewBox="0 0 1200 {SVG_H}" '
        f'width="100%" style="min-width:600px" preserveAspectRatio="xMidYMid meet">',
    ]

    # Lane background stripes
    for i in range(N_LANES):
        y_top = i * LANE_H
        bg = "#111420" if i % 2 == 0 else "#0d0f1a"
        parts.append(
            f'  <rect x="0" y="{y_top}" width="1200" height="{LANE_H}" fill="{bg}"/>'
        )

    # Axis area background
    parts.append(
        f'  <rect x="0" y="{AXIS_Y}" width="1200" height="28" fill="#090b10"/>'
    )

    # Vertical grid lines + time labels (N_TICKS evenly spaced)
    N_TICKS = 7
    for ti in range(N_TICKS + 1):
        frac = ti / N_TICKS
        x = LEFT + frac * TW
        total_s = frac * TS_RANGE * 60.0
        h_part = int(total_s // 3600) % 24
        m_part = int((total_s % 3600) // 60)
        s_part = int(total_s % 60)
        label = f"{h_part:02d}:{m_part:02d}:{s_part:02d}"
        parts.append(
            f'  <line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{AXIS_Y}" '
            f'stroke="#1e2232" stroke-width="1"/>'
        )
        anchor = "start" if ti == 0 else ("end" if ti == N_TICKS else "middle")
        parts.append(
            f'  <text x="{x:.1f}" y="{AXIS_Y + 18}" '
            f'text-anchor="{anchor}" class="ts-label">{label}</text>'
        )

    # Lanes: label + center line + event dots
    DOT_R = 5
    MIN_SEP = DOT_R * 2 + 2  # minimum px between dot centres

    for i, section in enumerate(sections):
        cy = i * LANE_H + LANE_H // 2
        color = pattern_colors[section.pattern_id]
        label = section.pattern_id.replace("_", " ")

        parts.append(
            f'  <text x="{LABEL_W}" y="{cy + 4}" '
            f'text-anchor="end" class="lane-label" fill="{color}">'
            f'{html.escape(label)}</text>'
        )
        parts.append(
            f'  <line x1="{LEFT}" y1="{cy}" x2="{RIGHT}" y2="{cy}" '
            f'stroke="{color}" stroke-width="0.5" opacity="0.3"/>'
        )

        # Collect events with timestamps, compute raw cx
        timed = [(LEFT + (evt.ts_minutes / TS_RANGE) * TW, evt)
                 for evt in section.events if evt.ts_minutes is not None]
        if not timed:
            continue

        # Sort by raw cx, then apply bidirectional min-separation:
        # 1) forward pass: push dots right if too close
        # 2) backward pass: pull back from RIGHT boundary, preserving spacing
        # 3) final left-clamp: shift whole lane right if first dot is left of LEFT
        timed.sort(key=lambda t: t[0])
        adj = [t[0] for t in timed]
        # Forward pass
        for k in range(1, len(adj)):
            if adj[k] - adj[k - 1] < MIN_SEP:
                adj[k] = adj[k - 1] + MIN_SEP
        # Backward pass from RIGHT
        if adj[-1] > RIGHT:
            adj[-1] = RIGHT
            for k in range(len(adj) - 2, -1, -1):
                if adj[k + 1] - adj[k] < MIN_SEP:
                    adj[k] = adj[k + 1] - MIN_SEP
        # Left clamp
        if adj[0] < LEFT:
            shift = LEFT - adj[0]
            adj = [x + shift for x in adj]

        for cx, (_, evt) in zip(adj, timed):
            sev_color = _SEVERITY_COLOR.get(evt.severity, "#8ec07c")
            tip = html.escape(evt.message[:80], quote=False)
            pid_esc = html.escape(evt.pattern_id, quote=True)
            parts.append(
                f'  <circle class="evt-dot" cx="{cx:.1f}" cy="{cy}" r="{DOT_R}" '
                f'fill="{sev_color}" stroke="{color}" stroke-width="1.5" '
                f'data-id="{evt.event_id}" data-pattern="{pid_esc}" '
                f'data-severity="{evt.severity}">'
                f'<title>{tip}</title></circle>'
            )

    parts.append("</svg>")
    return "\n".join(parts)


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(sections: List[PatternSection],
                pattern_colors: Dict[str, str],
                has_timestamps: bool,
                ts_max_minutes: float,
                title: str,
                input_file: str,
                generated_ts: str,
                total_events: int) -> str:

    # Inline JS data blobs
    patterns_js = json.dumps([
        {
            "id": s.pattern_id,
            "desc": s.description,
            "color": pattern_colors[s.pattern_id],
            "count": len(s.events),
        }
        for s in sections
    ], ensure_ascii=False)

    events_js = json.dumps([
        {
            "id": evt.event_id,
            "ts": evt.timestamp_str or "",
            "tsMin": evt.ts_minutes,
            "pattern": evt.pattern_id,
            "level": evt.log_level,
            "severity": evt.severity,
            "tag": evt.tag,
            "msg": evt.message[:200],
        }
        for s in sections
        for evt in s.events
    ], ensure_ascii=False)

    sev_color_js = json.dumps(_SEVERITY_COLOR)

    # Timeline section
    if has_timestamps:
        svg = _build_timeline_svg(sections, pattern_colors, ts_max_minutes)
        timeline_html = (
            '\n    <section id="timeline-section">\n'
            '      <h2>Timeline</h2>\n'
            '      <div id="timeline-wrap">\n        '
            + svg + '\n      </div>\n    </section>'
        )
    else:
        timeline_html = (
            '\n    <section id="timeline-section">\n'
            '      <p class="no-ts-note">No timestamps detected — timeline not available.</p>\n'
            '    </section>'
        )

    # Event card groups
    group_parts: List[str] = []
    for s in sections:
        color = pattern_colors[s.pattern_id]
        pid_esc_attr = html.escape(s.pattern_id, quote=True)
        pid_esc = html.escape(s.pattern_id)
        desc_esc = html.escape(s.description)
        n = len(s.events)

        card_lines: List[str] = []
        for evt in s.events:
            sev_color = _SEVERITY_COLOR.get(evt.severity, "#8ec07c")
            level_d = html.escape(evt.log_level or "?")
            tag_d = html.escape(evt.tag[:30]) if evt.tag else ""
            ts_d = html.escape(evt.timestamp_str or "")
            msg_d = html.escape(evt.message[:300])
            tag_span = f'<span class="ev-tag">{tag_d}</span>' if tag_d else ""
            ts_span = f'<span class="ev-ts">{ts_d}</span>' if ts_d else ""
            card_lines.append(
                f'          <div class="event-card" data-id="{evt.event_id}" '
                f'data-pattern="{pid_esc_attr}" data-severity="{evt.severity}">'
                f'<span class="lv-badge" '
                f'style="background:{sev_color}22;color:{sev_color};border-color:{sev_color}44">'
                f'{level_d}</span>'
                f'{tag_span}{ts_span}'
                f'<span class="ev-msg">{msg_d}</span>'
                f'</div>'
            )

        group_parts.append(
            f'      <div class="pattern-group" data-pattern="{pid_esc_attr}">\n'
            f'        <div class="group-hdr" onclick="toggleGroup(this)">\n'
            f'          <span class="group-dot" style="background:{color}"></span>\n'
            f'          <span class="group-title">{pid_esc}</span>\n'
            f'          <span class="group-desc">{desc_esc}</span>\n'
            f'          <span class="group-count" id="cnt-{pid_esc_attr}">'
            f'{n} event{"s" if n != 1 else ""}</span>\n'
            f'          <span class="chevron">&#9662;</span>\n'
            f'        </div>\n'
            f'        <div class="group-body">\n'
            + "\n".join(card_lines) + "\n"
            f'        </div>\n'
            f'      </div>'
        )

    # Pattern filter pills
    pill_parts: List[str] = []
    for s in sections:
        color = pattern_colors[s.pattern_id]
        pid_esc_attr = html.escape(s.pattern_id, quote=True)
        pid_esc = html.escape(s.pattern_id)
        pill_parts.append(
            f'          <button class="pill active" data-pattern="{pid_esc_attr}" '
            f'style="--c:{color}" onclick="togglePattern(this)">{pid_esc}</button>'
        )

    title_esc = html.escape(title)
    input_esc = html.escape(input_file)
    gen_esc = html.escape(generated_ts)
    n_pat = len(sections)
    pills_html = "\n".join(pill_parts)
    cards_html = "\n".join(group_parts)

    # JS uses {{ }} for literal braces inside the f-string
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_esc} — Interactive</title>
  <style>
{_CSS}
  </style>
</head>
<body>
  <div id="app">

    <header id="hdr">
      <h1>{title_esc}</h1>
      <div class="meta"><strong>Input:</strong> <code>{input_esc}</code>&nbsp;&nbsp;·&nbsp;&nbsp;<strong>Generated:</strong> {gen_esc}</div>
      <div class="stats">{total_events} event{"s" if total_events != 1 else ""} across {n_pat} pattern{"s" if n_pat != 1 else ""}</div>
    </header>

    <section id="controls">
      <div class="ctrl-row">
        <span class="ctrl-label">Patterns</span>
        <div class="pills">
{pills_html}
        </div>
      </div>
      <div class="ctrl-row">
        <span class="ctrl-label">Severity</span>
        <div class="sev-checks">
          <label><input type="checkbox" checked data-sev="critical" onchange="toggleSev(this)"><span class="sev-dot" style="background:#e83020"></span>critical</label>
          <label><input type="checkbox" checked data-sev="error" onchange="toggleSev(this)"><span class="sev-dot" style="background:#e85030"></span>error</label>
          <label><input type="checkbox" checked data-sev="warning" onchange="toggleSev(this)"><span class="sev-dot" style="background:#e8b840"></span>warning</label>
          <label><input type="checkbox" checked data-sev="info" onchange="toggleSev(this)"><span class="sev-dot" style="background:#8ec07c"></span>info</label>
        </div>
      </div>
    </section>
{timeline_html}

    <section id="events-section">
      <h2>Events &nbsp;<span id="visible-count"></span></h2>
{cards_html}
    </section>

  </div>

  <script>
const PATTERNS = {patterns_js};
const EVENTS = {events_js};
const SEV_COLOR = {sev_color_js};

const activePatterns = new Set(PATTERNS.map(p => p.id));
const activeSeverities = new Set(['info', 'warning', 'error', 'critical']);

function applyFilters() {{
  let visible = 0;
  document.querySelectorAll('.event-card').forEach(card => {{
    const show = activePatterns.has(card.dataset.pattern)
              && activeSeverities.has(card.dataset.severity);
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  }});

  document.querySelectorAll('.evt-dot').forEach(dot => {{
    const show = activePatterns.has(dot.dataset.pattern)
              && activeSeverities.has(dot.dataset.severity);
    dot.style.opacity = show ? '1' : '0.07';
    dot.style.pointerEvents = show ? '' : 'none';
  }});

  // Update per-group counts; hide empty groups
  document.querySelectorAll('.pattern-group').forEach(grp => {{
    const pid = grp.dataset.pattern;
    if (!activePatterns.has(pid)) {{
      grp.style.display = 'none';
      return;
    }}
    grp.style.display = '';
    const visInGrp = grp.querySelectorAll('.event-card:not([style*="display: none"]):not([style*="display:none"])').length;
    const cnt = document.getElementById('cnt-' + pid);
    if (cnt) cnt.textContent = visInGrp + ' event' + (visInGrp !== 1 ? 's' : '');
  }});

  const vc = document.getElementById('visible-count');
  if (vc) vc.textContent = '(' + visible + ' of ' + EVENTS.length + ')';
}}

function togglePattern(btn) {{
  const pid = btn.dataset.pattern;
  if (activePatterns.has(pid)) {{
    activePatterns.delete(pid);
    btn.classList.remove('active');
  }} else {{
    activePatterns.add(pid);
    btn.classList.add('active');
  }}
  applyFilters();
}}

function toggleSev(cb) {{
  if (cb.checked) activeSeverities.add(cb.dataset.sev);
  else activeSeverities.delete(cb.dataset.sev);
  applyFilters();
}}

function toggleGroup(hdr) {{
  const body = hdr.nextElementSibling;
  const chevron = hdr.querySelector('.chevron');
  const isCollapsed = body.style.display === 'none';
  body.style.display = isCollapsed ? '' : 'none';
  if (chevron) chevron.textContent = isCollapsed ? '▾' : '▸';
}}

document.addEventListener('DOMContentLoaded', () => {{
  // Wire up timeline dot → scroll to card
  document.querySelectorAll('.evt-dot').forEach(dot => {{
    dot.addEventListener('click', () => {{
      const card = document.querySelector('.event-card[data-id="' + dot.dataset.id + '"]');
      if (!card) return;
      // Expand group if collapsed
      const grp = card.closest('.pattern-group');
      if (grp) {{
        const body = grp.querySelector('.group-body');
        if (body && body.style.display === 'none') toggleGroup(grp.querySelector('.group-hdr'));
      }}
      card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      card.classList.add('highlighted');
      setTimeout(() => card.classList.remove('highlighted'), 1800);
    }});
  }});

  applyFilters();
}});
  </script>
</body>
</html>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def render(report_path: str) -> str:
    """Read report.md, build report_interactive.html alongside it.

    Returns the path to the generated HTML file.
    """
    report_path = os.path.abspath(report_path)
    with open(report_path, encoding="utf-8") as f:
        md_text = f.read()

    # Extract title + metadata from report.md header
    title_m = re.search(r"^# (.+)$", md_text, re.MULTILINE)
    title = title_m.group(1) if title_m else os.path.basename(report_path)

    input_m = re.search(r"^\*\*Input:\*\*\s+`(.+)`$", md_text, re.MULTILINE)
    input_file = input_m.group(1) if input_m else ""

    gen_m = re.search(r"^\*\*Generated:\*\*\s+(.+)$", md_text, re.MULTILINE)
    generated_ts = gen_m.group(1).strip() if gen_m else ""

    sections = _parse_report(md_text)
    _normalize_timestamps(sections)
    total_events = _assign_event_ids(sections)

    # Assign palette colors to patterns
    pattern_colors: Dict[str, str] = {}
    for i, s in enumerate(sections):
        pattern_colors[s.pattern_id] = _PATTERN_COLORS[i % len(_PATTERN_COLORS)]

    # Determine timeline availability
    ts_max = 0.0
    has_timestamps = False
    for s in sections:
        for evt in s.events:
            if evt.ts_minutes is not None:
                has_timestamps = True
                if evt.ts_minutes > ts_max:
                    ts_max = evt.ts_minutes

    html_content = _build_html(
        sections=sections,
        pattern_colors=pattern_colors,
        has_timestamps=has_timestamps,
        ts_max_minutes=ts_max,
        title=title,
        input_file=input_file,
        generated_ts=generated_ts,
        total_events=total_events,
    )

    out_path = os.path.splitext(report_path)[0] + "_interactive.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return out_path


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build a self-contained interactive HTML report from report.md."
    )
    parser.add_argument("--report", required=True, help="Path to report.md")
    args = parser.parse_args()

    print(f"  Input:  {args.report}", file=sys.stderr)
    out = render(args.report)
    print(f"  Output: {out}", file=sys.stderr)
    print(out)


if __name__ == "__main__":
    main()
