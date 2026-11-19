"""Per-dimension comparability of the evidence for one characteristic.

Automatic rule per dimension (over counted evidence items):
* any item without a *verified* value          -> UNKNOWN
* all verified values equal (normalized)       -> COMPARABLE
* verified values differ                       -> NOT_COMPARABLE
A rapporteur assessment in the spec (status + rationale) overrides the
automatic result and is reported as such.

``qualitative_conclusion`` is special: differing conclusions are not a
comparability failure but a disagreement; they are reported as COMPARABLE
with ``disagreement=True`` and drive the outcome to CONFLICTING.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import DIMENSIONS
from .spec import norm_text


@dataclass
class DimResult:
    dimension: str
    status: str
    method: str  # auto | assessment
    values: dict = field(default_factory=dict)  # item id -> value or None
    rationale: str = ""
    disagreement: bool = False


ORG_LEVEL_DIMENSIONS = ("qualitative_conclusion",)


def assess(char_id: str, items: list, assessments: dict, org_of: dict | None = None) -> dict:
    """org_of: item id -> organization id. Dimensions in ORG_LEVEL_DIMENSIONS
    are evaluated per organization (any verified value of the organization's
    items); all others per evidence item."""
    out = {}
    overrides = assessments.get(char_id, {})
    org_of = org_of or {}
    for dim in DIMENSIONS:
        vals = {}
        for it in items:
            c = it.dimensions.get(dim)
            vals[it.id] = c.value if (c is not None and c.verified) else None
        if dim in ORG_LEVEL_DIMENSIONS and org_of:
            per_org = {}
            for iid, v in vals.items():
                o = org_of.get(iid, iid)
                if v is not None:
                    per_org.setdefault(o, set()).add(v)
                else:
                    per_org.setdefault(o, set())
            vals = {o: (sorted(vs)[0] if len(vs) == 1 else (" | ".join(sorted(vs)) if vs else None))
                    for o, vs in per_org.items()}
        if dim in overrides:
            a = overrides[dim]
            out[dim] = DimResult(dim, a.status, "assessment", vals, a.rationale)
            continue
        if not items or any(v is None for v in vals.values()):
            missing = [i for i, v in vals.items() if v is None]
            out[dim] = DimResult(dim, "UNKNOWN", "auto", vals,
                                 f"no verified value for: {', '.join(missing)}" if missing else "no evidence")
            continue
        distinct = {norm_text(v) for v in vals.values()}
        if len(distinct) == 1:
            out[dim] = DimResult(dim, "COMPARABLE", "auto", vals, "identical verified values")
        elif dim == "qualitative_conclusion":
            out[dim] = DimResult(dim, "COMPARABLE", "auto", vals, "conclusions stated but differ",
                                 disagreement=True)
        else:
            out[dim] = DimResult(dim, "NOT_COMPARABLE", "auto", vals, "verified values differ")
    return out
