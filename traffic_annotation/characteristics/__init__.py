"""Stage 2: characteristic-level evidence evaluation and CROSSCHECK states.

Inputs are the original and annotated workbooks plus an *evidence spec*
(JSON, kept outside the repository) that links characteristics to datasets
through cited source cells. Every descriptive claim in the spec must quote
its cited cell verbatim; claims that cannot be verified are treated as
unknown. Statuses in the workbooks are never modified.
"""
