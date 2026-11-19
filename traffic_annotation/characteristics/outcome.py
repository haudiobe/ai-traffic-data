"""Agreement of comparable series across organizations.

Two aspects are evaluated separately at the conditions shared by all counted
organizations:

* **Trend agreement** (qualitative, from the data): the direction of change at
  each point (decrease / none / increase, using a dead band) and the shape of
  each series over the common conditions (decreasing / increasing / flat /
  non-monotonic). This is computed from the values. It is not the
  contributors' stated conclusion, which is the ``qualitative_conclusion``
  dimension.
* **Magnitude agreement** (quantitative): the gap between organization ranges
  at each point compared with ``magnitude_tolerance``.

Per point, CONSISTENT means the directions agree and the gap is within
tolerance. OPPOSITE means one organization increases while another decreases.
Everything else is MIXED. The overall result (unchanged from earlier
versions) is CONSISTENT if every point is consistent, and CONFLICTING if the
share of opposite points reaches ``conflicting_point_share`` or the stated
qualitative conclusions disagree. Otherwise it is MIXED. With fewer common
points than ``min_common_points`` it is INSUFFICIENT.

All thresholds are configuration values. While ``threshold_status`` is
EXPERIMENTAL, any outcome is non-authoritative.
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
    direction_agreement: str = ""  # AGREE | DIFFER | OPPOSITE
    magnitude: str = ""  # WITHIN | OUTSIDE (experimental tolerance)


@dataclass
class Outcome:
    result: str  # CONSISTENT | MIXED | CONFLICTING | INSUFFICIENT
    common_points: list = field(default_factory=list)
    points: list = field(default_factory=list)
    reason: str = ""
    trend: str = ""  # AGREE | PARTIAL | OPPOSITE | "" (insufficient)
    trend_reason: str = ""
    magnitude: str = ""  # AGREE | PARTIAL | DISAGREE | ""
    magnitude_reason: str = ""
    series_trends: dict = field(default_factory=dict)  # item id -> trend label


def direction(v: float, deadband: float) -> str:
    if v > deadband:
        return "increase"
    if v < -deadband:
        return "decrease"
    return "none"


def series_trend(values: list, deadband: float) -> str:
    """Shape of one series over ordered conditions; steps within the dead band are ignored."""
    steps = [b - a for a, b in zip(values, values[1:])]
    non_inc = all(s <= deadband for s in steps)
    non_dec = all(s >= -deadband for s in steps)
    if non_inc and non_dec:
        return "flat"
    if non_inc:
        return "decreasing"
    if non_dec:
        return "increasing"
    return "non-monotonic"


def _x(x):
    return f"{x * 100:g}%" if isinstance(x, float) else str(x)


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
            cls, dag = "OPPOSITE", "OPPOSITE"
        elif len(flat) == 1:
            dag = "AGREE"
            cls = "CONSISTENT" if gap <= tol else "MIXED"
        else:
            cls, dag = "MIXED", "DIFFER"
        points.append(Point(x, ranges, dirs, vals, max(allv) - min(allv), gap, cls, dag,
                            "WITHIN" if gap <= tol else "OUTSIDE"))
    n = len(points)
    n_opp = sum(p.classification == "OPPOSITE" for p in points)
    if conclusion_disagreement:
        res, why = "CONFLICTING", "stated qualitative conclusions differ"
    elif n_opp and n_opp / n >= cfg["conflicting_point_share"]:
        res, why = "CONFLICTING", f"{n_opp}/{n} points with opposite direction"
    elif all(p.classification == "CONSISTENT" for p in points):
        res, why = "CONSISTENT", f"all {n} common points consistent"
    else:
        n_c = sum(p.classification == "CONSISTENT" for p in points)
        res, why = "MIXED", f"{n_c}/{n} common points consistent"

    # trend agreement (direction per point + series shape)
    trends = {}
    for org in orgs:
        for iid, s in sorted(series_by_org[org].items()):
            trends[iid] = series_trend([s[x] for x in common], db)
    shapes = set(trends.values())
    n_dir = sum(p.direction_agreement == "AGREE" for p in points)
    if n_opp or {"increasing", "decreasing"} <= shapes:
        trend = "OPPOSITE"
    elif n_dir == n and len(shapes) == 1 and "non-monotonic" not in shapes:
        trend = "AGREE"
    else:
        trend = "PARTIAL"
    trend_reason = (f"direction agrees at {n_dir}/{n} common points; series shapes: "
                    + ", ".join(f"{k}={v}" for k, v in sorted(trends.items())))

    # magnitude agreement (experimental tolerance)
    within = [p for p in points if p.magnitude == "WITHIN"]
    outside = [p for p in points if p.magnitude == "OUTSIDE"]
    mag = "AGREE" if not outside else ("DISAGREE" if not within else "PARTIAL")
    mag_reason = f"gap between organizations within tolerance {tol:g} at {len(within)}/{n} common points"
    if outside:
        mag_reason += "; outside at " + ", ".join(f"{_x(p.x)} (gap {p.gap_between_orgs:.3f})" for p in outside)
    return Outcome(res, common, points, why, trend, trend_reason, mag, mag_reason, trends)
