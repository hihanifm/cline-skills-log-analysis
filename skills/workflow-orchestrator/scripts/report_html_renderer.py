"""
report_html_renderer.py — Convert report.md to a self-contained report.html.

Reads the markdown report produced by log_synthesizer_agent.py and emits a
styled, self-contained HTML file (no external dependencies) in the same
directory.

Usage:
    python3 report_html_renderer.py --report /path/to/out/<name>/report.md

Prints the HTML path to stdout. Progress goes to stderr.
Can also be imported and called via render(report_path).
"""

import argparse
import html
import os
import re
import sys


# ── Embedded CSS ──────────────────────────────────────────────────────────────

_HTML_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: #0f1117;
  color: #e8eaf0;
  max-width: 980px;
  margin: 0 auto;
  padding: 2rem 2.5rem 4rem;
  line-height: 1.65;
  font-size: 15px;
}

h1 {
  font-size: 1.6rem;
  font-weight: 700;
  color: #ffffff;
  margin: 1.75rem 0 0.5rem;
}

h2 {
  font-size: 1.15rem;
  font-weight: 600;
  color: #c8cfe8;
  margin: 1.5rem 0 0.4rem;
  padding-bottom: 0.3rem;
  border-bottom: 1px solid #2a2d3a;
}

p {
  margin: 0.45rem 0;
}

hr {
  border: none;
  border-top: 1px solid #2a2d3a;
  margin: 1.5rem 0;
}

pre {
  background: #1a1d27;
  border: 1px solid #2a2d3a;
  border-radius: 6px;
  padding: 1rem 1.25rem;
  overflow-x: auto;
  margin: 0.5rem 0 1rem;
}

pre code {
  font-family: 'Cascadia Code', 'Fira Code', Consolas, 'Courier New', monospace;
  font-size: 12.5px;
  color: #8ec07c;
  white-space: pre;
  background: none;
  border: none;
  padding: 0;
}

code {
  background: #1a1d27;
  border: 1px solid #2a2d3a;
  border-radius: 3px;
  padding: 0.1em 0.4em;
  font-family: 'Cascadia Code', 'Fira Code', Consolas, monospace;
  font-size: 0.88em;
  color: #e8b86d;
}

strong {
  color: #ffffff;
  font-weight: 600;
}

em {
  color: #9ab8d8;
  font-style: italic;
}

blockquote {
  border-left: 3px solid #e8903a;
  margin: 0.6rem 0;
  padding: 0.45rem 0.85rem;
  background: #1f1a0e;
  border-radius: 0 4px 4px 0;
  color: #e8c87a;
}
""".strip()


# ── Inline markdown conversion ────────────────────────────────────────────────

def _inline_md(text: str) -> str:
    """Convert inline markdown (bold, italic, backtick) to HTML.

    HTML-escapes the raw text first, then applies substitutions so that
    angle brackets inside log lines can't break the document structure.
    """
    escaped = html.escape(text, quote=False)
    # Inline code — must come before bold/italic so contents aren't re-processed
    escaped = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", escaped)
    # Bold
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    # Italic (single asterisk, not adjacent to another asterisk)
    escaped = re.sub(r"(?<!\*)\*(?!\*)([^*]+)(?<!\*)\*(?!\*)", r"<em>\1</em>", escaped)
    return escaped


# ── Markdown → HTML converter ─────────────────────────────────────────────────

def _md_to_html(md_text: str, title: str) -> str:
    """Convert report.md markdown text to a complete HTML document."""
    out = []
    in_code_block = False

    # Multi-line Cline placeholder comments may be stored as a single element
    # in the lines list containing literal \n, OR as separate lines.
    # We process the raw text line-by-line; a comment spanning multiple lines
    # is detected by tracking an open <!-- without a closing -->.
    in_html_comment = False
    comment_buf: list[str] = []

    for raw_line in md_text.splitlines():
        # ── Inside a fenced code block ──────────────────────────────────────
        if in_code_block:
            if raw_line.strip() == "```":
                out.append("</code></pre>")
                in_code_block = False
            else:
                out.append(html.escape(raw_line, quote=False))
            continue

        # ── Accumulating an HTML comment (Cline placeholder) ────────────────
        if in_html_comment:
            comment_buf.append(raw_line)
            if "-->" in raw_line:
                out.append("\n".join(comment_buf))
                comment_buf = []
                in_html_comment = False
            continue

        # ── Detect start of HTML comment ────────────────────────────────────
        if raw_line.startswith("<!--"):
            if "-->" in raw_line:
                # Single-line comment
                out.append(raw_line)
            else:
                in_html_comment = True
                comment_buf = [raw_line]
            continue

        # ── Fenced code block open ──────────────────────────────────────────
        if raw_line.strip() == "```":
            out.append("<pre><code>")
            in_code_block = True
            continue

        # ── Structural elements ─────────────────────────────────────────────
        stripped = raw_line.strip()

        if stripped == "---":
            out.append("<hr>")
            continue

        if stripped == "":
            # Preserve paragraph spacing via a blank line (ignored by browser
            # but keeps the source readable; CSS handles visual gaps)
            continue

        if raw_line.startswith("## "):
            out.append(f"<h2>{_inline_md(raw_line[3:])}</h2>")
            continue

        if raw_line.startswith("# "):
            out.append(f"<h1>{_inline_md(raw_line[2:])}</h1>")
            continue

        if raw_line.startswith("> "):
            out.append(f"<blockquote>{_inline_md(raw_line[2:])}</blockquote>")
            continue

        # ── Default: paragraph ──────────────────────────────────────────────
        out.append(f"<p>{_inline_md(raw_line)}</p>")

    # Close any unclosed code block (shouldn't happen with well-formed input)
    if in_code_block:
        out.append("</code></pre>")

    body = "\n".join(out)
    escaped_title = html.escape(title)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escaped_title}</title>
  <style>
{_HTML_CSS}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def render(report_path: str) -> str:
    """Read report_path (report.md), write report.html alongside it.

    Returns the path to the generated HTML file.
    """
    report_path = os.path.abspath(report_path)
    with open(report_path, encoding="utf-8") as f:
        md_text = f.read()

    # Derive title from first H1 in the document, fall back to filename
    title_match = re.search(r"^# (.+)$", md_text, re.MULTILINE)
    title = title_match.group(1) if title_match else os.path.basename(report_path)

    html_content = _md_to_html(md_text, title)

    html_path = os.path.splitext(report_path)[0] + ".html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return html_path


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert report.md to a self-contained report.html."
    )
    parser.add_argument("--report", required=True, help="Path to report.md")
    args = parser.parse_args()

    print(f"  Input:  {args.report}", file=sys.stderr)
    html_path = render(args.report)
    print(f"  Output: {html_path}", file=sys.stderr)
    print(html_path)


if __name__ == "__main__":
    main()
