"""Independence: collapse evidence to independent contributing organizations.

Campaigns, derivative records, repeated runs, network profiles, providers and
model variants contributed by the same organization count once. Evidence
whose organization is not identified is never counted as independent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Issue


def _norm(s) -> str:
    return re.sub(r"[\s,;/&+]+", " ", str(s or "")).strip().lower()


class OrgRegistry:
    def __init__(self, organizations):
        self.orgs = {o.id: o for o in organizations}
        self._alias = {}
        for o in organizations:
            for name in (o.id, o.name, *o.aliases):
                self._alias[_norm(name)] = o.id

    def resolve(self, name) -> str | None:
        if name is None:
            return None
        return self._alias.get(_norm(name))

    def name(self, org_id) -> str:
        return self.orgs[org_id].name if org_id in self.orgs else str(org_id)


@dataclass
class Independence:
    counted: list = field(default_factory=list)  # org ids (sorted)
    groups: dict = field(default_factory=dict)  # org id -> [item ids]
    excluded: dict = field(default_factory=dict)  # item id -> reason
    collapsed: list = field(default_factory=list)  # human-readable dedup decisions
    issues: list = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.counted)


_COLLAPSE_FIELDS = (("dataset", "datasets"), ("campaign", "campaigns"), ("variant", "variants"),
                    ("provider", "providers"), ("network_profile", "network profiles"),
                    ("run_group", "repeated runs"))


def independence(resolved_items, datasets: dict, registry: OrgRegistry, contributor_of: dict) -> Independence:
    """resolved_items: list of ResolvedItem. datasets: id -> DatasetRecord-like
    with .derived. contributor_of: dataset id -> contributor string."""
    res = Independence()
    for r in resolved_items:
        it = r.item
        ds = datasets.get(it.dataset)
        if ds is None:
            res.excluded[it.id] = "dataset not in catalogue"
            res.issues.append(Issue("ERROR", "mapping", it.id, f"dataset {it.dataset} not in catalogue"))
            continue
        if getattr(ds, "derived", False):
            res.excluded[it.id] = "derived/summary dataset"
            res.issues.append(Issue("WARNING", "independence", it.id,
                                    f"{it.dataset} is derived/summary data; not counted as evidence"))
            continue
        org = registry.resolve(it.organization)
        if org is None:
            res.excluded[it.id] = "organization not identified"
            res.issues.append(Issue("INFO", "independence", it.id,
                                    "contributing organization not identified; not counted as independent"))
            continue
        cat_org = registry.resolve(contributor_of.get(it.dataset))
        if cat_org is not None and cat_org != org:
            res.issues.append(Issue("WARNING", "mapping", it.id,
                                    f"organization {org} differs from catalogue contributor of {it.dataset}"))
        if not r.usable and it.series is not None:
            res.excluded[it.id] = "series could not be resolved"
            continue
        res.groups.setdefault(org, []).append(it.id)

    by_id = {r.item.id: r.item for r in resolved_items}
    for org, ids in sorted(res.groups.items()):
        items = [by_id[i] for i in ids]
        if len(items) > 1:
            parts = []
            for attr, label in _COLLAPSE_FIELDS:
                vals = sorted({getattr(i, attr) for i in items if getattr(i, attr)})
                if len(vals) > 1:
                    parts.append(f"{len(vals)} {label}")
            res.collapsed.append(f"{registry.name(org)}: {len(items)} evidence items"
                                 + (f" ({', '.join(parts)})" if parts else "") + " counted as 1 organization")
    res.counted = sorted(res.groups)
    return res
