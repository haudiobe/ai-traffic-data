"""Extract header metadata and quantitative claims from a contribution (.docx).

Only numbers and short header fields are extracted; the contribution text is
never copied into outputs beyond the matched claim phrase.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import config

_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}
_NUM = r"(\d+|" + "|".join(_NUM_WORDS) + r")"


def to_int(token: str) -> int:
    t = token.strip().lower()
    return int(t) if t.isdigit() else _NUM_WORDS[t]


def _sheet_pat(sheet: str) -> str:
    return re.escape(sheet).replace(r"\ ", r"\s+")


# claim key -> regex with one numeric group (case-insensitive)
CLAIM_PATTERNS = {
    "catalogue_rows": _NUM + r"-row\s+" + _sheet_pat(config.CATALOGUE_SHEET),
    "evidence_rows": _NUM + r"-row\s+" + _sheet_pat(config.EVIDENCE_SHEET),
    "provenance_rows": _NUM + r"-row\s+" + _sheet_pat(config.PROVENANCE_SHEET),
    "status_definition_rows": _NUM + r"-row\s+" + _sheet_pat(config.STATUS_DEFS_SHEET),
    "additional_fields": _NUM + r"\s+additional\b[^.]{0,80}?\bfields",
    "stable_records": r"\bSTABLE\s+to\s+" + _NUM,
    "submitted_records": r"\bSUBMITTED\s+to\s+" + _NUM,
    "cross_checked_no_records": r"CROSS_CHECKED\s*=\s*NO[^.]{0,60}?\ball\s+" + _NUM,
    "derived_records": r"Identified\s+" + _NUM + r"\b[^.]{0,80}?\bderived",
    "multi_source_characteristics": _NUM + r"\s+provisional\s+MULTI-SOURCE",
    "open_characteristics": r"\band\s+" + _NUM + r"\s+open\s+assessments",
}


@dataclass
class Contribution:
    path: Path
    header: dict
    claims: dict  # key -> (value, matched_phrase)
    paragraph_count: int


def _paragraphs(path: Path) -> list[str]:
    import docx  # python-docx

    d = docx.Document(str(path))
    out = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            out.extend(c.text for c in row.cells if c.text.strip())
    return out


_HEADER_KEYS = ("Source", "Title", "Spec", "Agenda item", "Document for")


def parse_text(paragraphs: list[str]) -> tuple[dict, dict]:
    header = {}
    for p in paragraphs[:20]:
        m = re.search(r"\b(S4\w*-\d{6})\b", p)
        if m and "tdoc" not in header:
            header["tdoc"] = m.group(1)
        for k in _HEADER_KEYS:
            if p.startswith(k + ":"):
                header[k.lower()] = p.split(":", 1)[1].strip()
    text = "\n".join(paragraphs)
    claims = {}
    for key, pat in CLAIM_PATTERNS.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            claims[key] = (to_int(m.group(1)), m.group(0)[:120])
    return header, claims


def load(path: Path) -> Contribution:
    paras = _paragraphs(Path(path))
    header, claims = parse_text(paras)
    return Contribution(Path(path), header, claims, len(paras))
