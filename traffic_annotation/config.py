"""Rule vocabulary for the Annex B.4 style dataset annotation.

Only generic vocabulary lives here (field names, status names, decision rules).
No source data, contributor names or document text.
"""
from __future__ import annotations

import re

INDEX_SHEET = "0. Index"

CATALOGUE_SHEET = "Dataset Catalogue"
EVIDENCE_SHEET = "Characteristic Evidence"
PROVENANCE_SHEET = "Provenance History"
STATUS_DEFS_SHEET = "Status Definitions"
REGISTER_SHEET = "Dataset Status Register"

ANNOTATION_SHEETS = (
    CATALOGUE_SHEET,
    EVIDENCE_SHEET,
    PROVENANCE_SHEET,
    STATUS_DEFS_SHEET,
    REGISTER_SHEET,
)

# B.4.4 metadata convention: mandatory fields first, then recommended fields.
MANDATORY_FIELDS = (
    "Dataset ID",
    "Contributor",
    "Creation date",
    "Scenario ID",
    "Scenario version",
    "Network profile ID(s)",
    "Application category",
    "Traffic direction",
    "Model provider",
    "Model name",
    "Execution date",
    "Number of runs",
)
RECOMMENDED_FIELDS = ("Model version", "Measurement tooling", "Statistical method")

# Additional traceability / governance columns used by the catalogue.
COL_PARENT = "Parent sheet"
COL_VARIANT = "Campaign / dataset variant"
COL_TDOCS = "Source TDoc(s)"
COL_PRIOR = "Prior agreement evidence"
COL_STATUS = "Assigned status"
COL_STATUS_BASIS = "Status date / basis"
COL_XCHECK = "CROSS_CHECKED"
COL_COMPLETENESS = "B.4.4 mandatory completeness"
COL_DERIVED = "Derived / summary dataset"
COL_RELATED = "Supersedes / related dataset"

DATASET_STATUSES = ("SUBMITTED", "CANDIDATE", "STABLE", "DEPRECATED")
EVIDENCE_FLAGS = ("UNASSESSED", "SINGLE-SOURCE", "MULTI-SOURCE")

# Values that mean "not available" -- treated as missing, never as data.
_MISSING_RE = re.compile(
    r"^\s*(|-+|–|—|n/?a|none|unknown|tbd|tbc|\?|"
    r"not\s+(identified|explicit|recorded|available|known|demonstrated|provided|stated)\b.*)\s*$",
    re.IGNORECASE,
)


def is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)):
        return False
    return bool(_MISSING_RE.match(str(value)))


def is_yes(value) -> bool:
    return value is not None and str(value).strip().upper().startswith("YES")


def expected_evidence_flag(n_independent_sources: int) -> str:
    """B.4.5: flag follows the number of independent contributing organizations."""
    if n_independent_sources <= 0:
        return "UNASSESSED"
    if n_independent_sources == 1:
        return "SINGLE-SOURCE"
    return "MULTI-SOURCE"


# Keyword hints used to PROPOSE candidate datasets for open characteristics.
# Proposals are always marked REVIEW; they are never applied automatically.
CHARACTERISTIC_CATEGORY_HINTS = {
    "cross-category": None,  # None = all non-derived datasets
    "chat": ("chat", "reasoning", "token"),
    "video understanding": ("video",),
    "realtime": ("real-time", "realtime", "webrtc"),
    "a2a": ("agent", "a2a", "mcp", "web search", "tool"),
    "interactive": ("chat", "real-time", "realtime", "agent", "interactive"),
}

FLOAT_REL_TOL = 1e-12
