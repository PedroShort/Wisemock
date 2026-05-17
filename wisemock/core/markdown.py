"""Markdown helpers — only what WiseMock actually renders.

The frontend `renderInline()` understands fenced code blocks (```` ```lang ```` …
```` ``` ````) and inline code (`` `tok` ``). This module provides one helper:

    autofence_code(text) -> str

Heuristic that wraps contiguous runs of code-like lines in `````python ````
fences when the input was *not* already authored as markdown. It exists to make
legacy JSONs (and AI parses that forgot to fence) render readably without
needing data migration. Forward-compatible: text that already contains a
``` fence is returned unchanged.
"""
import re

# A line "looks like code" if it matches any of these signals.
_CODE_LINE_PATTERNS = [
    # Common Python/JS keywords at line start
    re.compile(r'^\s*(def|class|for|while|if|elif|else|return|import|from|try'
               r'|except|finally|with|raise|yield|lambda|print|async|await'
               r'|function|var|let|const|=>)\b'),
    # Variable assignment:  foo = …, foo.bar = …, foo[i] = …
    re.compile(r'^\s*[A-Za-z_][\w.\[\]]*\s*=\s*\S'),
    # Standalone function call line:  foo(x, y)
    re.compile(r'^\s*[A-Za-z_][\w.]*\([^)]*\)\s*$'),
    # Indented continuation (likely a code body)
    re.compile(r'^[ \t]+\S'),
    # Closing brace / bracket / paren line (handles `}`, `)]`, `})`, `}],`, etc.)
    re.compile(r'^\s*[\}\]\)]+\s*[,;]?\s*$'),
    # Line ending in a colon and almost nothing else (def/if/for/etc.)
    re.compile(r'^\s*\S.*:\s*$'),
    # REPL-style prompts
    re.compile(r'^\s*(>>>|\.\.\.)\s'),
]


def _looks_like_code_line(line: str) -> bool:
    if not line.strip():
        return False
    return any(pat.search(line) for pat in _CODE_LINE_PATTERNS)


_BLANK_RUN_RE = re.compile(r"\n{3,}")


def _normalize_blank_lines(lines):
    """Strip leading/trailing blank lines and collapse runs of ≥2 blank lines
    inside a code block to a single blank. Operates on a list of lines and
    returns a new list."""
    # Strip ends
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    trimmed = lines[start:end]
    # Collapse runs of consecutive blank lines: keep at most 1.
    out = []
    prev_blank = False
    for line in trimmed:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        out.append(line)
        prev_blank = is_blank
    return out


_FENCE_RE = re.compile(r"```([a-zA-Z0-9_+\-]*)\n([\s\S]*?)```", re.MULTILINE)


def _clean_existing_fences(text: str) -> str:
    """Walk ``` … ``` blocks and normalize blank-line whitespace inside each."""
    def _clean(match):
        lang = match.group(1)
        body = match.group(2)
        cleaned = "\n".join(_normalize_blank_lines(body.split("\n")))
        return f"```{lang}\n{cleaned}\n```"
    return _FENCE_RE.sub(_clean, text)


def autofence_code(text: str) -> str:
    """Wrap contiguous runs of code-like lines in `````python ````` fences.

    Always normalizes whitespace inside any fenced block (existing or newly
    wrapped): leading/trailing blanks stripped, runs of ≥2 internal blanks
    collapsed to 1. PDF-extraction noise (page-break spacing) renders cleanly.

    No-op for the *outer* heuristic when the text already contains a ``` fence
    (we assume the producer formatted intentionally), but we still clean
    whitespace inside those existing fences.

    A "run" is ≥2 consecutive code-like lines, with blank lines allowed inside.
    Single isolated code-ish lines are left alone (they render fine as prose).
    """
    if not text:
        return text or ""
    if "```" in text:
        return _clean_existing_fences(text)

    lines = text.split("\n")
    if len(lines) < 2:
        return text

    # Per-line classification: True=code, False=prose, None=blank
    def classify(line):
        s = line.strip()
        if not s:
            return None
        return _looks_like_code_line(line)

    classes = [classify(line) for line in lines]

    out = []
    i = 0
    n = len(lines)
    while i < n:
        if classes[i] is True:
            # Extend run while we keep seeing code or blank lines.
            j = i
            last_code = i
            while j + 1 < n and classes[j + 1] is not False:
                j += 1
                if classes[j] is True:
                    last_code = j
            run = lines[i:last_code + 1]
            code_count = sum(1 for c in classes[i:last_code + 1] if c is True)
            if code_count >= 2:
                cleaned = _normalize_blank_lines(run)
                out.append("```python")
                out.extend(cleaned)
                out.append("```")
            else:
                out.extend(run)
            i = last_code + 1
        else:
            out.append(lines[i])
            i += 1
    return "\n".join(out)
