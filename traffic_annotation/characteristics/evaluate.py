"""Characteristic-level evaluation: evidence -> independence -> comparability
-> outcome -> CROSSCHECK state. Never modifies any workbook or status."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .. import config as s1config, crosscheck as stage1, workbook as wbm
from . import comparability, dedup, outcome as outcome_mod
from .model import DIMENSIONS, Issue, Spec, load_rules
from .spec import norm_text, resolve


@dataclass
class CharEval:
    id: str
    name: str
    recorded_flag: str
    recorded_assessment: str
    recorded_dataset_refs: str
    items: list = field(default_factory=list)  # ResolvedItem
    independence: dedup.Independence | None = None
    dims: dict = field(default_factory=dict)
    outcome: outcome_mod.Outcome | None = None
    state: str = "NOT_ASSESSED"
    state_reason: str = ""
    authority: str = "NOT_APPLICABLE"  # AUTHORITATIVE | PROVISIONAL | NOT_APPLICABLE
    authority_reason: str = ""
    basis_by_org: dict = field(default_factory=dict)  # verified primary metric basis -> [org]
    alt_basis_by_org: dict = field(default_factory=dict)  # verified alternative basis -> [org]
    basis_mismatch: str = ""
    basis_missing: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)


@dataclass
class Evaluation:
    characteristics: list
    stage1: stage1.Result
    registry: dedup.OrgRegistry
    spec: Spec
    rules: dict
    issues: list
    source_hashes: dict


def _state(ce: CharEval, rules: dict) -> None:
    ind = ce.independence
    n = ind.n if ind else 0
    if not ce.items:
        ce.state, ce.state_reason = "NOT_ASSESSED", "no evidence linked to this characteristic"
        return
    if n == 0:
        ce.state, ce.state_reason = "NOT_ASSESSED", "no evidence attributable to an identified organization"
        return
    if n < rules["min_independent_organizations"]:
        ce.state = "SINGLE_SOURCE"
        ce.state_reason = f"{n} independent organization(s); {rules['min_independent_organizations']} required"
        return
    eff = rules["dimension_status_effect"]
    req = rules["required_dimensions"]
    nc = [d for d in req if eff[ce.dims[d].status] == "not_comparable"]
    pend = [d for d in req if eff[ce.dims[d].status] == "pending"]
    # strict dimensions must be COMPARABLE; the effect mapping cannot relax them
    pend += [d for d in rules.get("strict_dimensions", [])
             if ce.dims[d].status != "COMPARABLE" and d not in nc and d not in pend]
    if nc:
        ce.state = "MULTI_SOURCE_NOT_COMPARABLE"
        ce.state_reason = f"{n} organizations; not comparable on: {', '.join(nc)}"
    elif pend:
        ce.state = "CROSSCHECK_PENDING"
        ce.state_reason = f"{n} organizations; comparability not demonstrated for: {', '.join(pend)}"
    elif ce.basis_mismatch:
        ce.state = "CROSSCHECK_PENDING"
        ce.state_reason = f"{n} organizations; {ce.basis_mismatch}"
    elif ce.outcome is None or ce.outcome.result == "INSUFFICIENT":
        ce.state = "CROSSCHECK_PENDING"
        ce.state_reason = f"{n} organizations; " + (ce.outcome.reason if ce.outcome else "no comparable series")
    else:
        ce.state = f"CROSSCHECKED_{ce.outcome.result}"
        ce.state_reason = f"{n} organizations; all required dimensions comparable; {ce.outcome.reason}"


def _authority(ce: CharEval, rules: dict) -> None:
    """A CROSSCHECKED state is authoritative only with approved thresholds and
    every required dimension demonstrably COMPARABLE (no relaxed mapping)."""
    if not ce.state.startswith("CROSSCHECKED_"):
        ce.authority = "NOT_APPLICABLE"
        ce.authority_reason = ("provisional outcome only, not applied (non-authoritative)"
                               if ce.outcome and ce.outcome.result != "INSUFFICIENT" else "")
        return
    why = []
    if rules.get("threshold_status", "EXPERIMENTAL") != "APPROVED":
        why.append("outcome thresholds are experimental")
    weak = [d for d in rules["required_dimensions"] if ce.dims[d].status != "COMPARABLE"]
    if weak:
        why.append("not demonstrably comparable: " + ", ".join(weak))
    ce.authority = "PROVISIONAL" if why else "AUTHORITATIVE"
    ce.authority_reason = "; ".join(why) or "approved thresholds; all required dimensions comparable"


def _bases(ce: CharEval, counted_ids: set, registry) -> None:
    prim, alt, missing = {}, {}, []
    for r in ce.items:
        if r.item.id not in counted_ids or not r.usable:
            continue
        org = registry.name(registry.resolve(r.item.organization))
        if r.basis:
            prim.setdefault(r.basis, set()).add(org)
        else:
            missing.append(r.item.id)
        if r.alt_basis:
            alt.setdefault(r.alt_basis, set()).add(org)
    ce.basis_by_org = {k: sorted(v) for k, v in sorted(prim.items())}
    ce.alt_basis_by_org = {k: sorted(v) for k, v in sorted(alt.items())}
    if len(prim) > 1:
        ce.basis_mismatch = ("metric basis differs across evidence: "
                             + "; ".join(f"{k}: {', '.join(v)}" for k, v in ce.basis_by_org.items()))
    ce.basis_missing = sorted(missing)


def _questions(ce: CharEval, counted_items: list, spec: Spec, registry) -> list:
    qs = []
    for dim in DIMENSIONS:
        d = ce.dims.get(dim)
        if d and d.status in ("PARTIAL", "UNKNOWN", "NOT_COMPARABLE"):
            qs.append(f"[{dim}] {d.status}: {d.rationale}")
        if d and d.disagreement:
            qs.append(f"[{dim}] stated conclusions differ")
    names = sorted({k for it in counted_items for k in it.facets})
    for name in names:
        vals = {}
        for it in counted_items:
            c = it.facets.get(name)
            vals[it.id] = c.value if c is not None and c.verified else None
        org_of = {it.id: registry.resolve(it.organization) for it in counted_items}
        by_org = {}
        for iid, v in vals.items():
            by_org.setdefault(org_of[iid], set()).add(v)
        flat = {norm_text(v) for v in vals.values() if v is not None}
        missing = sorted(i for i, v in vals.items() if v is None)
        if len(flat) > 1 and len(by_org) > 1:
            desc = "; ".join(f"{registry.name(o)}: {' | '.join(sorted(str(x) for x in vs if x is not None)) or 'n/a'}"
                             for o, vs in sorted(by_org.items()))
            qs.append(f"[facet:{name}] differs across organizations ({desc}); confirm effect on comparability")
        if missing:
            qs.append(f"[facet:{name}] not stated (verified) for: {', '.join(missing)}")
    if ce.basis_missing:
        qs.append(f"[metric_basis] denominator basis not stated (verified) for: {', '.join(ce.basis_missing)}")
    if ce.basis_mismatch:
        qs.append(f"[metric_basis] {ce.basis_mismatch}")
    for b, orgs in ce.alt_basis_by_org.items():
        if b not in ce.basis_by_org:
            qs.append(f"[metric_basis] alternative basis '{b}' reported by {', '.join(orgs)} only; "
                      "not used for cross-organization comparison")
    qs += [f"[rapporteur] {q}" for q in spec.questions.get(ce.id, [])]
    return qs


def _historical_gaps(datasets) -> list:
    """Aggregate missing B.4.4 metadata: one issue per field, not per record."""
    issues = []
    hist = [d for d in datasets if d.status == "STABLE" and not s1config.is_missing(d.prior_agreement)]
    new = [d for d in datasets if d not in hist]
    for f in s1config.MANDATORY_FIELDS:
        h = [d.dataset_id for d in hist if f in d.missing_mandatory]
        if h:
            issues.append(Issue("QUALIFIED_GAP", "historical-metadata", f,
                                f"{len(h)} of {len(hist)} historical agreed datasets do not record '{f}' "
                                "(results retained)",
                                "None required for retention; complete when contributor information is available"))
        n = [d.dataset_id for d in new if f in d.missing_mandatory]
        if n:
            issues.append(Issue("WARNING", "metadata", f,
                                f"{len(n)} non-historical dataset(s) lack '{f}': {', '.join(n)}",
                                "Complete before any CANDIDATE assignment"))
    return issues


def run(original: Path, annotated: Path, spec: Spec, rules: dict | None = None) -> Evaluation:
    rules = rules or load_rules()
    hashes = {"original": wbm.sha256(Path(original)), "annotated": wbm.sha256(Path(annotated))}
    s1 = stage1.run(original, annotated)
    registry = dedup.OrgRegistry(spec.organizations)
    datasets = {d.dataset_id: d for d in s1.datasets}
    contributor_of = {d.dataset_id: d.contributor for d in s1.datasets}
    wb = wbm.load(Path(original))
    issues: list[Issue] = []

    # characteristic universe: workbook register + spec
    chars = {}
    for e in s1.evidence:
        chars[e["characteristic_id"]] = CharEval(e["characteristic_id"], e["characteristic"], e["flag_stated"],
                                                 e["assessment_status"], e["dataset_refs"])
    for c in spec.characteristics:
        if c.id not in chars:
            issues.append(Issue("WARNING", "mapping", c.id, "characteristic in spec but not in the workbook register"))
            chars[c.id] = CharEval(c.id, c.name, "", "", "")
        elif c.name and not chars[c.id].name:
            chars[c.id].name = c.name

    for it in spec.evidence:
        if it.characteristic not in chars:
            issues.append(Issue("ERROR", "mapping", it.id, f"unknown characteristic {it.characteristic}"))
            continue
        r = resolve(it, wb, rules["reported_value_tolerance"])
        chars[it.characteristic].items.append(r)
        issues.extend(r.issues)

    for ce in chars.values():
        ce.independence = dedup.independence(ce.items, datasets, registry, contributor_of)
        issues.extend(ce.independence.issues)
        counted_ids = {i for ids in ce.independence.groups.values() for i in ids}
        counted = [r.item for r in ce.items if r.item.id in counted_ids]
        org_of = {it.id: registry.resolve(it.organization) for it in counted}
        ce.dims = comparability.assess(ce.id, counted, spec.assessments, org_of)
        _bases(ce, counted_ids, registry)
        if ce.independence.n >= 2:
            by_org = {}
            for r in ce.items:
                if r.item.id in counted_ids and r.usable:
                    by_org.setdefault(registry.resolve(r.item.organization), {})[r.item.id] = r.rel_change
            ce.outcome = outcome_mod.evaluate(by_org, rules["outcome"],
                                              ce.dims["qualitative_conclusion"].disagreement)
        _state(ce, rules)
        _authority(ce, rules)
        ce.open_questions = _questions(ce, counted, spec, registry) if ce.items else []

        # compare with what the workbook records (never changed)
        if ce.items:
            used = sorted({r.item.dataset for r in ce.items})
            s1e = next((e for e in s1.evidence if e["characteristic_id"] == ce.id), None)
            if s1e is not None:
                ref_ids = sorted(set(s1e["dataset_ids_resolved"] or s1e["dataset_ids_proposed"]))
                if ref_ids and ref_ids != used:
                    issues.append(Issue("WARNING", "mapping", ce.id,
                                        f"evidence datasets {used} differ from workbook reference {ref_ids}"))
            issues.append(Issue("INFO", "state", ce.id,
                                f"recorded: {ce.recorded_flag or '-'} / {ce.recorded_assessment or '-'}; "
                                f"evaluated: {ce.state} [{ce.authority}] (recorded values not changed)"))
    issues.extend(_historical_gaps(s1.datasets))

    # de-duplicate identical issues, deterministic order
    uniq = {(i.severity, i.category, i.subject, i.message): i for i in issues}
    issues = sorted(uniq.values(), key=lambda i: i.key())
    return Evaluation(sorted(chars.values(), key=lambda c: c.id), s1, registry, spec, rules, issues, hashes)
