"""Deterministic resume structuring with provenance.

Every extracted item keeps the character offsets (and page, when known) of the passage it came
from. Missing sections are reported as missing; nothing is inferred or filled in.
"""
from __future__ import annotations

import re

from .evidence import page_for_offset
from .lexicon import find_skills

SECTION_ALIASES = {
    "summary": ["summary", "profile", "objective", "about me", "professional summary"],
    "skills": ["skills", "technical skills", "core competencies", "competencies", "technologies", "tools"],
    "experience": ["experience", "work experience", "professional experience", "employment history",
                   "employment", "work history", "career history"],
    "education": ["education", "academic background", "qualifications", "academic qualifications"],
    "projects": ["projects", "personal projects", "key projects"],
    "certifications": ["certifications", "certificates", "licenses", "licences"],
    "achievements": ["achievements", "awards", "accomplishments", "honors", "honours"],
}
_HEADING_LOOKUP = {alias: key for key, aliases in SECTION_ALIASES.items() for alias in aliases}
_HEADING_RE = re.compile(r"^\s*([A-Za-z][A-Za-z &/]{1,40}?)\s*:?\s*$")
DEGREE_RE = re.compile(r"\b(b\.?sc|m\.?sc|b\.?tech|m\.?tech|b\.?e\.?|m\.?e\.?|bachelor|master|ph\.?d|doctorate|mba|"
                       r"associate degree|diploma|b\.?a\.?|m\.?a\.?|b\.?com|m\.?com)\b", re.IGNORECASE)
YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\b(?:\s+of)?(?:\s+experience)?", re.IGNORECASE)
DATE_RANGE_RE = re.compile(r"\b((?:19|20)\d{2})\s*(?:-|–|to)\s*((?:19|20)\d{2}|present|current|now)\b", re.IGNORECASE)
CERT_RE = re.compile(r"\b(certified|certification|certificate)\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _detect_sections(text: str) -> list[dict]:
    sections = []
    pos = 0
    for line in text.split("\n"):
        m = _HEADING_RE.match(line)
        if m and len(line.strip()) <= 42:
            key = _HEADING_LOOKUP.get(m.group(1).strip().lower())
            if key:
                sections.append({"section": key, "heading_start": pos, "start": pos + len(line) + 1})
        pos += len(line) + 1
    for i, s in enumerate(sections):
        s["end"] = sections[i + 1]["heading_start"] if i + 1 < len(sections) else len(text)
    return sections


def _lines_in(text: str, start: int, end: int):
    pos = start
    for line in text[start:end].split("\n"):
        if line.strip():
            lead = len(line) - len(line.lstrip())
            yield line.strip(), pos + lead, pos + lead + len(line.strip())
        pos += len(line) + 1


def _item(value: str, start: int, end: int, pages, **extra) -> dict:
    return {"value": value, "start": start, "end": end, "page": page_for_offset(pages, start), **extra}


def parse_resume(text: str, pages: list[dict] | None = None) -> dict:
    text = text or ""
    sections = _detect_sections(text)
    by_name = {}
    for s in sections:
        by_name.setdefault(s["section"], s)

    def section_lines(name: str):
        s = by_name.get(name)
        return list(_lines_in(text, s["start"], s["end"])) if s else []

    skills = [_item(s["skill"], s["start"], s["end"], pages, matched=s["matched"]) for s in find_skills(text)]

    education = [_item(v, a, b, pages) for v, a, b in section_lines("education")]
    if not education:
        education = [_item(v, a, b, pages, located_by="degree keyword")
                     for v, a, b in _lines_in(text, 0, len(text)) if DEGREE_RE.search(v)][:8]

    certifications = [_item(v, a, b, pages) for v, a, b in section_lines("certifications")]
    if not certifications:
        certifications = [_item(v, a, b, pages, located_by="certification keyword")
                          for v, a, b in _lines_in(text, 0, len(text)) if CERT_RE.search(v)][:8]

    experience = [_item(v, a, b, pages) for v, a, b in section_lines("experience")][:60]
    employment = []
    for v, a, b in _lines_in(text, 0, len(text)):
        m = DATE_RANGE_RE.search(v)
        if m:
            employment.append(_item(v, a, b, pages, from_year=m.group(1), to_year=m.group(2)))
    years_statements = []
    for m in YEARS_RE.finditer(text):
        years_statements.append({"years": float(m.group(1)), "start": m.start(), "end": m.end(),
                                 "quote": text[m.start():m.end()], "page": page_for_offset(pages, m.start())})

    result = {
        "skills": skills,
        "education": education,
        "experience": experience,
        "employment_history": employment[:40],
        "projects": [_item(v, a, b, pages) for v, a, b in section_lines("projects")][:40],
        "certifications": certifications,
        "achievements": [_item(v, a, b, pages) for v, a, b in section_lines("achievements")][:30],
        "summary": [_item(v, a, b, pages) for v, a, b in section_lines("summary")][:10],
        "years_of_experience_statements": years_statements[:20],
        "sections_detected": [s["section"] for s in sections],
        "contact_present": bool(EMAIL_RE.search(text)),
    }
    result["missing_fields"] = [k for k in ("skills", "education", "experience", "projects", "certifications")
                                if not result[k]]
    result["parser"] = "deterministic-v1"
    return result
