"""Markdown to HTML for QLabel/QTextDocument.

Qt's rich text supports a subset of HTML/CSS, so code blocks get inline styles instead of
classes. Raw HTML in model output is escaped, never rendered. Colors come from the active
theme so code blocks follow light/dark mode.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt

from . import theme

_md = MarkdownIt("commonmark", {"html": False, "linkify": False})
_md.enable("strikethrough")

_CODE_ATTR = re.compile(r"<code[^>]*>")


def render_markdown(text: str) -> str:
    code_bg = theme.CODE_BG
    code_fg = theme.CODE_FG
    accent = theme.ACCENT
    pre = (f'<pre style="background:{code_bg};color:{code_fg};padding:8px;'
           "font-family:'JetBrains Mono',monospace;white-space:pre-wrap;"
           'margin:4px 0;">')
    code = (f'<code style="background:{theme.PANEL_2};color:{accent};font-family:'
            "'JetBrains Mono',monospace;" '">')
    html = _md.render(text or "")
    html = html.replace("<pre>", pre)
    html = _CODE_ATTR.sub(code, html)
    return html
