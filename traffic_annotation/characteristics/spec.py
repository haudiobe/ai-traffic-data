"""Load an evidence spec and resolve it against a workbook.

Resolution rules (no inference):
* a Claim is *verified* only if its quote occurs verbatim (whitespace- and
  dash-normalized) in the cited cell; unverified claims count as UNKNOWN;
* numeric values are read from cited cells only; a numeric constant (e.g. a
  denominator) must also occur inside its verified quote;
* x-axis conditions are parsed from the cited header cells.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl.utils.cell import range_boundaries

from .model import (DIMENSIONS, Assessment, Characteristic, Claim, Denominator, EvidenceItem, Issue,
                    Organization, Series, SourceRef, Spec, DIM_STATUSES)

SPEC_SCHEMA = "traffic-annotation/evidence-spec@1"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _ref(d):
    if not d:
        return None
    return SourceRef(d["sheet"], d["cell"], d["quote"])


def _claim(d):
    if d is None:
        return Claim(None)
    if isinstance(d, str):
        return Claim(d)
    return Claim(d.get("value"), _ref(d.get("source")), d.get("note", ""))


def _den(d):
    if not d:
        return None
    return Denominator(d.get("value"), _ref(d.get("source")), d.get("cells"))


def _series(d):
    if not d:
        return None
    return Series(
        sheet=d["sheet"], x_cells=d["x_cells"], baseline_cell=d["baseline_cell"], value_cells=d["value_cells"],
        x_parse=d.get("x_parse", "percent"), value_kind=d.get("value_kind", "count"),
        denominator=_den(d.get("denominator")), alt_denominator=_den(d.get("alt_denominator")),
        reported_change_cells=d.get("reported_change_cells"),
        alt_reported_change_cells=d.get("alt_reported_change_cells"),
    )


def parse_spec(data: dict) -> Spec:
    if data.get("schema") != SPEC_SCHEMA:
        raise ValueError(f"spec schema must be {SPEC_SCHEMA!r}")
    orgs = [Organization(o["id"], o["name"], tuple(o.get("aliases", ()))) for o in data.get("organizations", [])]
    chars = [Characteristic(c["id"], c.get("name", ""), c.get("metric", ""), c.get("x_variable", ""),
                            c.get("unit", "")) for c in data.get("characteristics", [])]
    items = []
    for e in data.get("evidence", []):
        dims = {k: _claim(v) for k, v in (e.get("dimensions") or {}).items()}
        bad = set(dims) - set(DIMENSIONS)
        if bad:
            raise ValueError(f"{e['id']}: unknown dimensions {sorted(bad)}")
        items.append(EvidenceItem(
            id=e["id"], characteristic=e["characteristic"], dataset=e["dataset"],
            organization=e.get("organization"), variant=e.get("variant", ""), campaign=e.get("campaign", ""),
            provider=e.get("provider", ""), network_profile=e.get("network_profile", ""),
            run_group=e.get("run_group", ""), series=_series(e.get("series")), dimensions=dims,
            facets={k: _claim(v) for k, v in (e.get("facets") or {}).items()},
        ))
    ids = [i.id for i in items]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise ValueError(f"duplicate evidence ids: {dup}")
    assessments = {}
    for cid, dims in (data.get("assessments") or {}).items():
        for dim, a in dims.items():
            if dim not in DIMENSIONS or a["status"] not in DIM_STATUSES:
                raise ValueError(f"invalid assessment {cid}/{dim}")
            if not a.get("rationale"):
                raise ValueError(f"assessment {cid}/{dim} requires a rationale")
            assessments.setdefault(cid, {})[dim] = Assessment(a["status"], a["rationale"])
    return Spec(orgs, chars, items, assessments, {k: list(v) for k, v in (data.get("questions") or {}).items()})


def load_spec(path: Path) -> Spec:
    return parse_spec(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
_DASH = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = dict.fromkeys(map(ord, "“”„″"), '"')


def norm_text(s) -> str:
    s = str(s or "").translate(_DASH).translate(_QUOTES).replace("×", "x")
    return re.sub(r"\s+", " ", s).strip().lower()


def _cells(ws, rng):
    min_col, min_row, max_col, max_row = range_boundaries(rng)
    out = []
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            out.append(ws.cell(r, c).value)
    return out


def parse_condition(label, mode: str):
    if mode == "percent":
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(label or ""))
        return round(float(m.group(1)) / 100, 10) if m else None
    if mode == "number":
        try:
            return float(label)
        except (TypeError, ValueError):
            return None
    if mode == "label":
        return str(label).strip() if label is not None else None
    raise ValueError(f"unknown x_parse {mode!r}")


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


@dataclass
class ResolvedItem:
    item: EvidenceItem
    x: list = field(default_factory=list)
    baseline: float | None = None
    values: list = field(default_factory=list)
    rel_change: dict = field(default_factory=dict)  # x -> relative change vs baseline
    denominators: list = field(default_factory=list)
    alt_rel_change: dict = field(default_factory=dict)
    reported_change: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    cited_cells: list = field(default_factory=list)  # "sheet!cell"

    @property
    def usable(self) -> bool:
        return bool(self.rel_change)


def verify_ref(wb, ref: SourceRef, issues: list, subject: str) -> bool:
    if ref.sheet not in wb.sheetnames:
        issues.append(Issue("ERROR", "citation", subject, f"cited sheet '{ref.sheet}' not found",
                            "Fix the citation"))
        return False
    val = wb[ref.sheet][ref.cell].value
    if val is None:
        issues.append(Issue("ERROR", "citation", subject, f"cited cell {ref.sheet}!{ref.cell} is empty",
                            "Fix the citation"))
        return False
    if norm_text(ref.quote) not in norm_text(val):
        issues.append(Issue("ERROR", "citation", subject,
                            f"quote not found verbatim in {ref.sheet}!{ref.cell}: '{ref.quote[:80]}'",
                            "Quote the source exactly; unverified claims are treated as UNKNOWN"))
        return False
    return True


def _verify_claim(wb, claim: Claim, issues, subject) -> None:
    if claim.value is None:
        claim.verified = None
        return
    if claim.source is None:
        claim.verified = False
        issues.append(Issue("WARNING", "citation", subject, "claim has no source citation",
                            "Add a verbatim source quote; uncited claims are treated as UNKNOWN"))
        return
    claim.verified = verify_ref(wb, claim.source, issues, subject)


def _constant_in_quote(value, quote) -> bool:
    if value is None:
        return False
    v = float(value)
    for tok in re.findall(r"\d[\d\s,.]*", quote):
        t = tok.replace(" ", "").replace(",", "").rstrip(".")
        try:
            if float(t) == v:
                return True
        except ValueError:
            continue
    return False


def resolve(item: EvidenceItem, wb, tol: float) -> ResolvedItem:
    r = ResolvedItem(item)
    for dim, claim in item.dimensions.items():
        _verify_claim(wb, claim, r.issues, f"{item.id}/{dim}")
        if claim.source:
            r.cited_cells.append(f"{claim.source.sheet}!{claim.source.cell}")
    for name, claim in item.facets.items():
        _verify_claim(wb, claim, r.issues, f"{item.id}/facet:{name}")
        if claim.source:
            r.cited_cells.append(f"{claim.source.sheet}!{claim.source.cell}")
    s = item.series
    if s is None:
        return r
    if s.sheet not in wb.sheetnames:
        r.issues.append(Issue("ERROR", "series", item.id, f"series sheet '{s.sheet}' not found"))
        return r
    ws = wb[s.sheet]
    r.cited_cells += [f"{s.sheet}!{s.x_cells}", f"{s.sheet}!{s.baseline_cell}", f"{s.sheet}!{s.value_cells}"]
    labels = _cells(ws, s.x_cells)
    raw_vals = _cells(ws, s.value_cells)
    if len(labels) != len(raw_vals):
        r.issues.append(Issue("ERROR", "series", item.id,
                              f"x_cells ({len(labels)}) and value_cells ({len(raw_vals)}) differ in length"))
        return r
    xs = [parse_condition(l, s.x_parse) for l in labels]
    if any(x is None for x in xs):
        r.issues.append(Issue("ERROR", "series", item.id, f"unparsable condition labels: {labels}"))
        return r
    vals = [_num(v) for v in raw_vals]
    base = _num(ws[s.baseline_cell].value)
    if base is None or any(v is None for v in vals):
        r.issues.append(Issue("ERROR", "series", item.id, "baseline or values are not numeric in the source",
                              "Point the series at numeric cells (formulas are not evaluated)"))
        return r
    if base == 0:
        r.issues.append(Issue("ERROR", "series", item.id, "baseline is zero; relative change undefined"))
        return r
    r.x, r.baseline, r.values = xs, base, vals
    r.rel_change = {x: (v - base) / base for x, v in zip(xs, vals)}

    # denominators (must be cited; constants must be inside a verified quote)
    for label, den in (("denominator", s.denominator), ("alt_denominator", s.alt_denominator)):
        if den is None:
            continue
        if den.cells:
            dvals = [_num(v) for v in _cells(ws, den.cells)]
            r.cited_cells.append(f"{s.sheet}!{den.cells}")
            if len(dvals) != len(xs) or any(v in (None, 0) for v in dvals):
                r.issues.append(Issue("ERROR", "series", item.id, f"{label} cells invalid"))
                continue
            if label == "denominator":
                r.denominators = dvals
            else:
                # relative change of accuracy with per-condition denominators;
                # baseline denominator is the cell left of the range start
                min_col, min_row, _, _ = range_boundaries(den.cells)
                bden = _num(ws.cell(min_row, min_col - 1).value)
                if not bden:
                    r.issues.append(Issue("WARNING", "series", item.id, f"{label}: baseline denominator not numeric"))
                    continue
                b_acc = base / bden
                r.alt_rel_change = {x: (v / d) / b_acc - 1 for x, v, d in zip(xs, vals, dvals)}
        elif den.value is not None:
            ok = den.source is not None and verify_ref(wb, den.source, r.issues, f"{item.id}/{label}")
            if ok and not _constant_in_quote(den.value, den.source.quote):
                r.issues.append(Issue("ERROR", "citation", f"{item.id}/{label}",
                                      f"value {den.value} does not occur in the cited quote"))
                ok = False
            if ok:
                r.denominators = [float(den.value)] * len(xs)
                r.cited_cells.append(f"{den.source.sheet}!{den.source.cell}")
            else:
                r.issues.append(Issue("WARNING", "series", item.id, f"{label} not verified; not used"))

    # reported change cross-verification (definition check)
    for cells, computed, store, label in (
            (s.reported_change_cells, r.rel_change, r.reported_change, "reported change"),
            (s.alt_reported_change_cells, r.alt_rel_change, {}, "reported change (alt. denominator)")):
        if not cells:
            continue
        rep = _cells(ws, cells)
        r.cited_cells.append(f"{s.sheet}!{cells}")
        if len(rep) != len(xs):
            r.issues.append(Issue("ERROR", "series", item.id, f"{label} cells length mismatch"))
            continue
        n_ok, n_bad = 0, 0
        for x, v in zip(xs, rep):
            nv = _num(v)
            if nv is None or x not in computed:
                continue
            store[x] = nv
            if abs(nv - computed[x]) > tol:
                n_bad += 1
                r.issues.append(Issue("WARNING", "definition", item.id,
                                      f"{label} at x={x:g} is not reproduced from source counts within "
                                      f"tolerance {tol} (|difference| = {abs(nv - computed[x]):.4f})",
                                      "Confirm the metric definition / rounding used by the contributor"))
            else:
                n_ok += 1
        if n_ok and not n_bad:
            r.issues.append(Issue("INFO", "definition", item.id,
                                  f"{n_ok} {label} values reproduced from source counts within tolerance {tol}"))
    return r
