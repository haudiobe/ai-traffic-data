"""Command line entry point.

    python -m traffic_annotation --original ORIG.xlsx --annotated B4.xlsx \
        [--contribution CONTRIB.docx] --out OUTDIR [--fail-on FAIL]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import contribution as contrib_mod, crosscheck, report, safety


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="traffic-annotation", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", required=True, type=Path, help="original collated results workbook")
    ap.add_argument("--annotated", required=True, type=Path, help="annotated (Annex B.4) workbook")
    ap.add_argument("--contribution", type=Path, help="contribution .docx with quantitative claims")
    ap.add_argument("--out", required=True, type=Path, help="output directory (must be outside the repo)")
    ap.add_argument("--prefix", default="crosscheck", help="output file prefix")
    ap.add_argument("--fail-on", choices=["FAIL", "REVIEW", "never"], default="FAIL",
                    help="exit non-zero if findings with this decision exist")
    a = ap.parse_args(argv)

    safety.assert_outside_repo(a.original, a.annotated, a.contribution, a.out)
    for p in (a.original, a.annotated, a.contribution):
        if p is not None and not p.is_file():
            ap.error(f"not a file: {p}")

    c = contrib_mod.load(a.contribution) if a.contribution else None
    res = crosscheck.run(a.original, a.annotated, c)
    a.out.mkdir(parents=True, exist_ok=True)
    x = report.write_review_xlsx(res, a.out / f"{a.prefix}_review.xlsx")
    m = report.write_markdown(res, a.out / f"{a.prefix}_report.md")
    j = report.write_json(res, a.out / f"{a.prefix}_normalized_catalogue.json")

    s = report.decision_summary(res)
    print(f"datasets={len(res.datasets)} characteristics={len(res.evidence)} "
          f"PASS={s['PASS']} ACCEPT={s['ACCEPT']} REVIEW={s['REVIEW']} FAIL={s['FAIL']}")
    for p in (x, m, j):
        print(f"wrote {p}")
    if a.fail_on == "FAIL" and s["FAIL"]:
        return 2
    if a.fail_on == "REVIEW" and (s["FAIL"] or s["REVIEW"]):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
