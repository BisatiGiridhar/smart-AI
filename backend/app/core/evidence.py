"""Evidence location and deterministic citation verification.

A citation is valid only if the quoted text exists in the stored resume text at (or within a
small window of) the stated offsets. Citations that cannot be located are rejected.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .text_utils import passage_around, term_pattern


@dataclass
class Citation:
    quote: str
    start: int
    end: int
    page: int | None = None


@dataclass
class VerificationResult:
    valid: bool
    reason: str
    located_start: int | None = None
    located_end: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _ws_regex(quote: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in quote.split()]
    return re.compile(r"\s+".join(parts), re.IGNORECASE)


def verify_citation(text: str, quote: str, start: int | None, end: int | None,
                    window: int = 60, min_len: int = 3) -> VerificationResult:
    if not quote or len(quote.strip()) < min_len:
        return VerificationResult(False, "quote_too_short")
    if not text:
        return VerificationResult(False, "source_text_empty")
    if start is not None and end is not None and 0 <= start < end <= len(text):
        if text[start:end] == quote:
            return VerificationResult(True, "exact_match", start, end)
    pat = _ws_regex(quote.strip())
    matches = list(pat.finditer(text))
    if not matches:
        return VerificationResult(False, "quote_not_found")
    if start is None:
        return VerificationResult(False, "location_missing")
    for m in matches:
        if abs(m.start() - start) <= window:
            return VerificationResult(True, "matched_near_stated_location", m.start(), m.end())
    return VerificationResult(False, "location_mismatch", matches[0].start(), matches[0].end())


def page_for_offset(pages: list[dict] | None, offset: int) -> int | None:
    for p in pages or []:
        if p.get("start", 0) <= offset < p.get("end", 0):
            return p.get("page")
    return None


def find_term_evidence(text: str, terms: tuple[str, ...] | list[str], pages: list[dict] | None = None,
                       max_hits: int = 3) -> list[dict]:
    """Return verified evidence passages containing any of ``terms`` (whole-word, case-insensitive)."""
    hits: list[dict] = []
    seen_lines: set[tuple[int, int]] = set()
    for term in terms:
        if not term:
            continue
        for m in term_pattern(term).finditer(text):
            ps, pe = passage_around(text, m.start(), m.end())
            if (ps, pe) in seen_lines:
                continue
            seen_lines.add((ps, pe))
            quote = text[ps:pe].strip()
            lead = len(text[ps:pe]) - len(text[ps:pe].lstrip())
            qs = ps + lead
            qe = qs + len(quote)
            check = verify_citation(text, quote, qs, qe)
            if not check.valid:
                continue
            hits.append({"quote": quote, "start": qs, "end": qe, "match_start": m.start(),
                         "match_end": m.end(), "matched_term": term,
                         "page": page_for_offset(pages, m.start()), "verification": check.reason,
                         "kind": "direct"})
            if len(hits) >= max_hits:
                return hits
    return hits
