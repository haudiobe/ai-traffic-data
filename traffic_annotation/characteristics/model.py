"""Data model for characteristic-level evidence evaluation."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

DIMENSIONS = (
    "definition",
    "units",
    "direction",
    "scenario",
    "measurement_layer",
    "baseline",
    "network_conditions",
    "statistical_basis",
    "qualitative_conclusion",
)
DIM_STATUSES = ("COMPARABLE", "PARTIAL", "NOT_COMPARABLE", "UNKNOWN")

STATES = (
    "NOT_ASSESSED",
    "SINGLE_SOURCE",
    "MULTI_SOURCE_NOT_COMPARABLE",
    "CROSSCHECK_PENDING",
    "CROSSCHECKED_CONSISTENT",
    "CROSSCHECKED_MIXED",
    "CROSSCHECKED_CONFLICTING",
)
OUTCOMES = ("CONSISTENT", "MIXED", "CONFLICTING", "INSUFFICIENT")

SEVERITIES = ("ERROR", "WARNING", "QUALIFIED_GAP", "INFO")

THRESHOLD_STATUSES = ("EXPERIMENTAL", "APPROVED")
AUTHORITY = ("AUTHORITATIVE", "PROVISIONAL", "NOT_APPLICABLE")


@dataclass(frozen=True)
class SourceRef:
    sheet: str
    cell: str
    quote: str


@dataclass
class Claim:
    """A descriptive value with a verbatim source citation."""
    value: str | None
    source: SourceRef | None = None
    note: str = ""
    verified: bool | None = None  # set during resolution


@dataclass
class Denominator:
    value: float | None = None
    source: SourceRef | None = None
    cells: str | None = None  # per-condition denominators (range)
    basis: str | None = None  # e.g. "all_questions", "received_at_server"; needs a verified source


@dataclass
class Series:
    sheet: str
    x_cells: str
    baseline_cell: str
    value_cells: str
    x_parse: str = "percent"
    value_kind: str = "count"  # count | fraction
    denominator: Denominator | None = None
    alt_denominator: Denominator | None = None
    reported_change_cells: str | None = None
    alt_reported_change_cells: str | None = None


@dataclass
class EvidenceItem:
    id: str
    characteristic: str
    dataset: str
    organization: str | None
    variant: str = ""
    campaign: str = ""
    provider: str = ""
    network_profile: str = ""
    run_group: str = ""
    series: Series | None = None
    dimensions: dict = field(default_factory=dict)  # dim -> Claim
    facets: dict = field(default_factory=dict)  # name -> Claim


@dataclass
class Organization:
    id: str
    name: str
    aliases: tuple = ()


@dataclass
class Characteristic:
    id: str
    name: str = ""
    metric: str = ""
    x_variable: str = ""
    unit: str = ""


@dataclass
class Assessment:
    status: str
    rationale: str


@dataclass
class Spec:
    organizations: list
    characteristics: list
    evidence: list
    assessments: dict  # char -> dim -> Assessment
    questions: dict  # char -> [str]


@dataclass
class Issue:
    severity: str
    category: str
    subject: str
    message: str
    action: str = ""

    def key(self):
        return (SEVERITIES.index(self.severity), self.category, self.subject, self.message)


def load_rules(path: Path | None = None) -> dict:
    if path is None:
        text = resources.files(__package__).joinpath("rules.json").read_text(encoding="utf-8")
    else:
        text = Path(path).read_text(encoding="utf-8")
    rules = json.loads(text)
    unknown = set(rules["required_dimensions"]) - set(DIMENSIONS)
    if unknown:
        raise ValueError(f"unknown dimensions in rules: {sorted(unknown)}")
    rules.setdefault("strict_dimensions", [])
    unknown = set(rules["strict_dimensions"]) - set(DIMENSIONS)
    if unknown:
        raise ValueError(f"unknown strict dimensions in rules: {sorted(unknown)}")
    rules.setdefault("threshold_status", "EXPERIMENTAL")
    if rules["threshold_status"] not in THRESHOLD_STATUSES:
        raise ValueError(f"threshold_status must be one of {THRESHOLD_STATUSES}")
    for st, eff in rules["dimension_status_effect"].items():
        if st not in DIM_STATUSES or eff not in ("ok", "pending", "not_comparable"):
            raise ValueError(f"invalid dimension_status_effect {st}: {eff}")
    return rules
