"""Loads the configurable skills lexicon and finds skill mentions with offsets."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from .text_utils import term_pattern

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "skills_lexicon.json"


@lru_cache(maxsize=4)
def load_lexicon(path: str | None = None) -> dict[str, tuple[str, ...]]:
    p = Path(path or os.environ.get("SKILLS_LEXICON_PATH") or DEFAULT_PATH)
    data = json.loads(p.read_text(encoding="utf-8"))
    out: dict[str, tuple[str, ...]] = {}
    for canonical, aliases in data["skills"].items():
        terms = {canonical.lower(), *[a.lower() for a in aliases]}
        out[canonical] = tuple(sorted(terms, key=len, reverse=True))
    return out


def find_skills(text: str, lexicon: dict[str, tuple[str, ...]] | None = None) -> list[dict]:
    """Return each canonical skill found, with the first matching span. Nothing is inferred."""
    lex = lexicon or load_lexicon()
    found = []
    for canonical, terms in lex.items():
        best = None
        for t in terms:
            m = term_pattern(t).search(text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), m.end(), t)
        if best:
            found.append({"skill": canonical, "start": best[0], "end": best[1], "matched": text[best[0]:best[1]],
                          "alias": best[2]})
    found.sort(key=lambda d: d["start"])
    return found


def terms_for(skill: str, lexicon: dict[str, tuple[str, ...]] | None = None) -> tuple[str, ...]:
    lex = lexicon or load_lexicon()
    return lex.get(skill, (skill.lower(),))
