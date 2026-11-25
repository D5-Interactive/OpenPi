"""Markdown to HTML for QLabel/QTextDocument.

Qt's rich text supports a subset of HTML/CSS, so code blocks get inline styles instead of
classes. Raw HTML in model output is escaped, never rendered.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"html": False, "linkify": False})
_md.enable("strikethrough")

_PRE = ('<pre style="background:#1b1f27;color:#c9d1d9;padding:8px;'
        "font-family:'JetBrains Mono',monospace;white-space:pre-wrap;"
        'margin:4px 0;">')
_CODE = ('<code style="background:#232833;color:#c9d1d9;font-family:'
         "'JetBrains Mono',monospace;" '">')
_CODE_ATTR = re.compile(r"<code[^>]*>")


def render_markdown(text: str) -> str:
    html = _md.render(text or "")
    html = html.replace("<pre>", _PRE)
    html = _CODE_ATTR.sub(_CODE, html)
    return html
