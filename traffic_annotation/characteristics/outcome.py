"""Quantitative agreement of comparable series across organizations.

At each condition shared by all counted organizations:
* each series' relative change is classified as decrease / none / increase
  using a dead band;
* an organization's range is [min, max] over its own variants;
* the point is CONSISTENT if all organizations share one direction and their
  ranges are within ``magnitude_tolerance`` of each other, OPPOSITE if one
  organization increases while another decreases, otherwise MIXED.
Overall: CONSISTENT if every point is consistent; CONFLICTING if the share of
opposite points reaches ``conflicting_point_share`` or stated qualitative
conclusions disagree; otherwise MIXED. Fewer common points than
``min_common_points`` -> INSUFFICIENT.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Point:
    x: float
    org_ranges: dict  # org -> (min, max)
    org_directions: dict  # org -> sorted list of directions
    series_values: dict  # item id -> value
    spread_all: float  # max - min over all series
    gap_between_orgs: float  # minimal distance between org ranges (0 if overlapping)
    classification: str  # CONSISTENT | MIXED | OPPOSITE


@dataclass
class Outcome:
    result: str  # CONSISTENT | MIXED | CONFLICTING | INSUFFICIENT
    common_points: list = field(default_factory=list)
    points: list = field(default_factory=list)
    reason: str = ""


def direction(v: float, deadband: float) -> str:
    if v > deadband:
        return "increase"
    if v < -deadband:
        return "decrease"
    return "none"


def evaluate(series_by_org: dict, cfg: dict, conclusion_disagreement: bool = False) -> Outcome:
    """series_by_org: org -> {item_id: {x: rel_change}}"""
    db, tol = cfg["deadband"], cfg["magnitude_tolerance"]
    orgs = sorted(series_by_org)
    if len(orgs) < 2:
        return Outcome("INSUFFICIENT", reason="fewer than two organizations with series")
    common = None
    for org in orgs:
        xs = set()
        for s in series_by_org[org].values():
            xs |= set(s)
        common = xs if common is None else common & xs
    common = sorted(common or [])
    if len(common) < cfg["min_common_points"]:
        return Outcome("INSUFFICIENT", common, reason=f"{len(common)} common condition point(s); "
                                                      f"{cfg['min_common_points']} required")
    points = []
    for x in common:
        ranges, dirs, vals = {}, {}, {}
        for org in orgs:
            v = [s[x] for s in series_by_org[org].values() if x in s]
            for iid, s in series_by_org[org].items():
                if x in s:
                    vals[iid] = s[x]
            ranges[org] = (min(v), max(v))
            dirs[org] = sorted({direction(a, db) for a in v})
        allv = list(vals.values())
        lo_max = max(r[0] for r in ranges.values())
        hi_min = min(r[1] for r in ranges.values())
        gap = max(0.0, lo_max - hi_min)
        flat = set().union(*map(set, dirs.values()))
        if "increase" in flat and "decrease" in flat and any(
                d == ["increase"] for d in dirs.values()) and any(d == ["decrease"] for d in dirs.values()):
            cls = "OPPOSITE"
        elif len(flat) == 1 and gap <= tol:
            cls = "CONSISTENT"
        else:
            cls = "MIXED"
        points.append(Point(x, ranges, dirs, vals, max(allv) - min(allv), gap, cls))
    n_opp = sum(p.classification == "OPPOSITE" for p in points)
    if conclusion_disagreement:
        res, why = "CONFLICTING", "stated qualitative conclusions differ"
    elif n_opp and n_opp / len(points) >= cfg["conflicting_point_share"]:
        res, why = "CONFLICTING", f"{n_opp}/{len(points)} points with opposite direction"
    elif all(p.classification == "CONSISTENT" for p in points):
        res, why = "CONSISTENT", f"all {len(points)} common points consistent"
    else:
        n_c = sum(p.classification == "CONSISTENT" for p in points)
        res, why = "MIXED", f"{n_c}/{len(points)} common points consistent"
    return Outcome(res, common, points, why)
