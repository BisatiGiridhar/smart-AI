"""Deterministic job-description analysis and rubric drafting.

The drafted rubric is a *draft*: it must be reviewed and approved by a recruiter before it is
used for decision support. Skills that cannot be placed in a required or preferred section are
marked for recruiter classification instead of being guessed.
"""
from __future__ import annotations

import re

from .lexicon import find_skills, terms_for

REQUIRED_HEADINGS = ["requirements", "required", "required skills", "must have", "must-have",
                     "minimum qualifications", "qualifications", "what you need", "what you'll need",
                     "basic qualifications", "key skills", "skills"]
PREFERRED_HEADINGS = ["preferred", "preferred qualifications", "nice to have", "nice-to-have", "bonus",
                      "desirable", "good to have", "plus", "preferred skills"]
RESP_HEADINGS = ["responsibilities", "what you'll do", "what you will do", "duties", "role", "key responsibilities",
                 "the role", "about the role"]
YEARS_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs?)", re.IGNORECASE)
PREF_INLINE_RE = re.compile(r"\b(preferred|nice to have|a plus|bonus|desirable|ideally)\b", re.IGNORECASE)


def _classify_heading(line: str) -> str | None:
    s = line.strip().strip(":").strip().lower()
    if not s or len(s) > 40:
        return None
    if s in PREFERRED_HEADINGS:
        return "preferred"
    if s in RESP_HEADINGS:
        return "responsibilities"
    if s in REQUIRED_HEADINGS:
        return "required"
    return None


def analyze_job(text: str, title: str | None = None) -> dict:
    text = text or ""
    blocks: list[dict] = []
    pos = 0
    current = None
    for line in text.split("\n"):
        kind = _classify_heading(line)
        if kind:
            if current:
                current["end"] = pos
            current = {"kind": kind, "start": pos + len(line) + 1, "end": len(text)}
            blocks.append(current)
        pos += len(line) + 1

    def block_of(offset: int) -> str | None:
        for b in blocks:
            if b["start"] <= offset < b["end"]:
                return b["kind"]
        return None

    required, preferred, unclassified = [], [], []
    for s in find_skills(text):
        kind = block_of(s["start"])
        line_start = text.rfind("\n", 0, s["start"]) + 1
        line_end = text.find("\n", s["start"])
        line = text[line_start: line_end if line_end != -1 else len(text)]
        entry = {"skill": s["skill"], "start": s["start"], "end": s["end"], "quote": line.strip()}
        if kind == "preferred" or PREF_INLINE_RE.search(line):
            preferred.append(entry)
        elif kind == "required":
            required.append(entry)
        else:
            unclassified.append(entry)

    years = None
    ym = YEARS_RE.search(text)
    if ym:
        years = {"min_years": float(ym.group(1)), "quote": text[ym.start():ym.end()], "start": ym.start(), "end": ym.end()}
    responsibilities = []
    for b in blocks:
        if b["kind"] == "responsibilities":
            for ln in text[b["start"]:b["end"]].split("\n"):
                if ln.strip():
                    responsibilities.append(ln.strip(" -*•\t"))
    first_line = next((ln.strip() for ln in text.split("\n") if ln.strip()), "")
    return {
        "title": title or first_line[:120],
        "required_skills": required,
        "preferred_skills": preferred,
        "unclassified_skills": unclassified,
        "experience_requirement": years,
        "responsibilities": responsibilities[:30],
        "sections_detected": [b["kind"] for b in blocks],
        "analyzer": "deterministic-v1",
        "notes": ([] if blocks else ["No requirement headings were found; skill priority needs recruiter review."]),
    }


def draft_rubric(analysis: dict, max_rating: float = 4.0) -> list[dict]:
    """Draft criteria from an analysis. Required=2, preferred=1, unclassified=1 (flagged)."""
    criteria: list[dict] = []
    seen: set[str] = set()

    def add(skill: str, weight: float, required: bool, note: str | None = None):
        if skill in seen:
            return
        seen.add(skill)
        criteria.append({"id": "skill:" + re.sub(r"[^a-z0-9]+", "-", skill.lower()).strip("-"), "label": skill,
                         "kind": "skill", "weight": weight, "max_rating": max_rating,
                         "terms": list(terms_for(skill)), "required": required, "note": note})

    for s in analysis.get("required_skills", []):
        add(s["skill"], 2.0, True)
    for s in analysis.get("preferred_skills", []):
        add(s["skill"], 1.0, False)
    for s in analysis.get("unclassified_skills", []):
        add(s["skill"], 1.0, False, "Priority not stated in the job description; review the weight.")
    exp = analysis.get("experience_requirement")
    if exp:
        criteria.append({"id": "experience-years", "label": f"At least {exp['min_years']:g} years of experience",
                         "kind": "experience_years", "weight": 2.0, "max_rating": max_rating, "terms": [],
                         "required": True, "min_years": exp["min_years"], "note": None})
    return criteria
