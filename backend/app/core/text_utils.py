"""Small text helpers shared by the deterministic core (no framework dependencies)."""
from __future__ import annotations

import re
import unicodedata

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-/]*")

STOPWORDS = frozenset(
    """a an and are as at be been but by for from has have in into is it its of on or that the
    their there these this to was were will with within we you your our us they them he she his her
    i me my not no so than then too very can could should would may might must also such per via""".split()
)


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").lower()


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for raw in TOKEN_RE.findall(normalize(text)):
        tok = raw.strip(".-/")
        if not tok or tok in STOPWORDS:
            continue
        if len(tok) == 1 and tok not in {"c", "r"}:
            continue
        out.append(tok)
    return out


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def line_bounds(text: str, pos: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return start, end


def passage_around(text: str, start: int, end: int, max_len: int = 320) -> tuple[int, int]:
    """Expand a match to its surrounding line, clipped to ``max_len`` characters."""
    ls, le = line_bounds(text, start)
    if le - ls <= max_len:
        return ls, le
    centre = (start + end) // 2
    ps = max(ls, centre - max_len // 2)
    pe = min(le, ps + max_len)
    return ps, pe


def term_pattern(term: str) -> re.Pattern[str]:
    """Word-boundary pattern that also works for C++, C#, .NET, Node.js and similar terms."""
    escaped = re.escape(term.lower())
    return re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9+#])", re.IGNORECASE)
