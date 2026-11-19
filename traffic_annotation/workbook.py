"""Read-only workbook access, sheet statistics and sheet-name resolution."""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from . import config


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: Path):
    """Open a workbook without modifying it (formulas kept as text)."""
    return openpyxl.load_workbook(Path(path), data_only=False)


@dataclass
class SheetStats:
    name: str
    max_row: int
    max_col: int
    nonempty_cells: int
    numeric_cells: int
    text_cells: int
    formula_cells: int
    merged_ranges: int
    nonempty_rows: int
    replacement_chars: int  # U+FFFD occurrences (encoding damage)


def sheet_stats(ws) -> SheetStats:
    nonempty = numeric = text = formulas = repl = 0
    rows_with_data = 0
    for row in ws.iter_rows():
        row_has = False
        for c in row:
            v = c.value
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            row_has = True
            nonempty += 1
            if isinstance(v, bool):
                text += 1
            elif isinstance(v, (int, float)):
                numeric += 1
            elif isinstance(v, str) and v.startswith("="):
                formulas += 1
            else:
                text += 1
                if isinstance(v, str):
                    repl += v.count("�")
        rows_with_data += row_has
    return SheetStats(
        ws.title, ws.max_row, ws.max_column, nonempty, numeric, text, formulas,
        len(ws.merged_cells.ranges), rows_with_data, repl,
    )


@dataclass
class SheetDiff:
    name: str
    differing_cells: int = 0
    float_noise_cells: int = 0
    max_rel_float_diff: float = 0.0
    samples: list = field(default_factory=list)  # coordinates only, never values

    @property
    def identical(self) -> bool:
        return self.differing_cells == 0


def _floats_close(a, b) -> tuple[bool, float]:
    if isinstance(a, bool) or isinstance(b, bool):
        return False, math.inf
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        denom = max(abs(a), abs(b), 1e-300)
        rel = abs(a - b) / denom
        return rel <= config.FLOAT_REL_TOL, rel
    return False, math.inf


def cell_map(ws) -> dict:
    """{(row, col): value} for non-empty cells. Does not create cells
    (ws.cell() would, and that silently grows max_row)."""
    return {(c.row, c.column): c.value for row in ws.iter_rows() for c in row if c.value is not None}


def diff_sheets(ws_a, ws_b) -> SheetDiff:
    from openpyxl.utils import get_column_letter

    d = SheetDiff(ws_a.title)
    ma, mb = cell_map(ws_a), cell_map(ws_b)
    for key in sorted(ma.keys() | mb.keys()):
        va, vb = ma.get(key), mb.get(key)
        if va == vb:
            continue
        close, rel = _floats_close(va, vb)
        if close:
            d.float_noise_cells += 1
            d.max_rel_float_diff = max(d.max_rel_float_diff, rel)
            continue
        d.differing_cells += 1
        if len(d.samples) < 10:
            d.samples.append(f"{get_column_letter(key[1])}{key[0]}")
    return d


def read_table(ws, header_row: int = 1):
    """Return (headers, records). Each record has '_row' with its sheet row."""
    headers = [
        (str(c.value).strip() if c.value is not None else "")
        for c in ws[header_row]
    ]
    records = []
    for r in range(header_row + 1, ws.max_row + 1):
        vals = [ws.cell(r, i + 1).value for i in range(len(headers))]
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in vals):
            continue
        rec = {h: v for h, v in zip(headers, vals) if h}
        rec["_row"] = r
        records.append(rec)
    return headers, records


def count_data_rows(ws, header_row: int = 1) -> int:
    """Independent raw count of non-empty rows below the header (cross-check)."""
    n = 0
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if any(v is not None and str(v).strip() for v in row):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Sheet-name resolution
# ---------------------------------------------------------------------------
_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―�"), "-")
_CLAUSE_RE = re.compile(r"^\s*(\d+(?:\.\d+)*[a-z]?)(?=[\s_]|$)", re.IGNORECASE)


def norm_name(name) -> str:
    s = str(name or "").translate(_DASHES).lower()
    s = s.replace("real-time", "realtime")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clause_of(name) -> str | None:
    m = _CLAUSE_RE.match(str(name or ""))
    return m.group(1).lower() if m else None


def resolve_sheet(name, sheetnames) -> tuple[str | None, str]:
    """Resolve a sheet reference. Returns (sheet, method).

    method is one of: exact, normalized, clause, ambiguous-clause, unresolved.
    """
    if name is None:
        return None, "unresolved"
    if name in sheetnames:
        return name, "exact"
    n = norm_name(name)
    for s in sheetnames:
        if norm_name(s) == n:
            return s, "normalized"
    cl = clause_of(name)
    if cl:
        hits = [s for s in sheetnames if clause_of(s) == cl]
        if len(hits) == 1:
            return hits[0], "clause"
        if len(hits) > 1:
            return None, "ambiguous-clause"
    return None, "unresolved"
