"""Controlled counterfactual substitution for fairness audits.

Only the auditor-supplied token is replaced. The function proves that nothing else changed by
comparing the text outside the replaced spans. Protected characteristics are never inferred.
"""
from __future__ import annotations

import difflib
import re


def substitute(text: str, original: str, replacement: str) -> tuple[str, list[dict]]:
    if not original.strip():
        raise ValueError("original token must not be empty")
    pat = re.compile(rf"(?<![\w]){re.escape(original)}(?![\w])")
    spans = []
    out, last = [], 0
    for m in pat.finditer(text):
        out.append(text[last:m.start()])
        out.append(replacement)
        spans.append({"start": m.start(), "end": m.end()})
        last = m.end()
    out.append(text[last:])
    return "".join(out), spans


def unexpected_changes(original_text: str, new_text: str, original: str, replacement: str) -> list[str]:
    """Word-level diff; returns any change other than ``original`` -> ``replacement``."""
    a, b = original_text.split(), new_text.split()
    orig_words, repl_words = original.split(), replacement.split()
    problems = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        old_seg, new_seg = a[i1:i2], b[j1:j2]
        cleaned_old = [w for w in old_seg if not any(o in w for o in orig_words)]
        cleaned_new = [w for w in new_seg if not any(r in w for r in repl_words)]
        if cleaned_old or cleaned_new:
            problems.append(f"{tag}: {' '.join(old_seg)[:80]!r} -> {' '.join(new_seg)[:80]!r}")
    return problems


def rank_positions(scores: dict[str, float | None]) -> list[str]:
    """Deterministic ordering: scored candidates by score desc, then unscored, then id."""
    return sorted(scores, key=lambda k: (scores[k] is None, -(scores[k] or 0.0), k))


def pairwise_flip_rate(before: list[str], after: list[str], focus: str) -> float | None:
    """Fraction of (focus, other) pairs whose relative order differs between two rankings."""
    others = [d for d in before if d != focus and d in after]
    if not others or focus not in before or focus not in after:
        return None
    pb, pa = {d: i for i, d in enumerate(before)}, {d: i for i, d in enumerate(after)}
    flips = sum(1 for o in others if (pb[focus] < pb[o]) != (pa[focus] < pa[o]))
    return flips / len(others)
