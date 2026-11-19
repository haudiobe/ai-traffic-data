"""Stage 2 command line.

    python -m traffic_annotation.characteristics --original ORIG.xlsx --annotated B4.xlsx \
        --spec evidence_spec.json --out OUTDIR [--rules rules.json] [--sheets-dry-run] \
        [--fail-on ERROR|WARNING|never]

All paths must be outside the repository. Inputs are opened read-only and
their SHA-256 is compared before and after the run.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .. import safety, workbook as wbm
from . import evaluate, gsheets, review
from .model import AUTHORITY, STATES, load_rules
from .spec import load_spec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="traffic-annotation-characteristics", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--original", required=True, type=Path)
    ap.add_argument("--annotated", required=True, type=Path)
    ap.add_argument("--spec", required=True, type=Path, help="evidence spec JSON (outside the repo)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--rules", type=Path, help="override crosscheck rules JSON")
    ap.add_argument("--prefix", default="characteristic_crosscheck")
    ap.add_argument("--sheets-dry-run", action="store_true", help="write a Google Sheets sync plan (no network)")
    ap.add_argument("--sheets-title", default="Characteristic CROSSCHECK review")
    ap.add_argument("--fail-on", choices=["ERROR", "WARNING", "never"], default="ERROR")
    a = ap.parse_args(argv)

    safety.assert_outside_repo(a.original, a.annotated, a.spec, a.out, a.rules)
    inputs = [a.original, a.annotated, a.spec]
    before = {p: wbm.sha256(p) for p in inputs}

    ev = evaluate.run(a.original, a.annotated, load_spec(a.spec), load_rules(a.rules))
    a.out.mkdir(parents=True, exist_ok=True)
    written = [review.write_xlsx(ev, a.out / f"{a.prefix}_review.xlsx"),
               review.write_markdown(ev, a.out / f"{a.prefix}_report.md")]
    written += review.write_json(ev, a.out / "normalized")
    if a.sheets_dry_run:
        plan = gsheets.build_plan(review.tables(ev), a.sheets_title)
        written.append(gsheets.write_plan(plan, a.out / "sheets_sync_plan.json"))
        for line in gsheets.SheetsSync(dry_run=True).run(plan):
            print(f"[dry-run] {line}")

    after = {p: wbm.sha256(p) for p in inputs}
    if before != after:
        print("ERROR: input files changed during the run", file=sys.stderr)
        return 3
    states = Counter(c.state for c in ev.characteristics)
    sev = Counter(i.severity for i in ev.issues)
    print("characteristics=" + str(len(ev.characteristics)) + " "
          + " ".join(f"{s}={states.get(s, 0)}" for s in STATES))
    auth = Counter(c.authority for c in ev.characteristics)
    print("authority: " + " ".join(f"{k}={auth.get(k, 0)}" for k in AUTHORITY)
          + f" (thresholds {ev.rules.get('threshold_status', 'EXPERIMENTAL')})")
    print(" ".join(f"{k}={sev.get(k, 0)}" for k in ("ERROR", "WARNING", "QUALIFIED_GAP", "INFO")))
    print("inputs unchanged (SHA-256 verified)")
    for p in written:
        print(f"wrote {p}")
    if a.fail_on == "ERROR" and sev.get("ERROR"):
        return 2
    if a.fail_on == "WARNING" and (sev.get("ERROR") or sev.get("WARNING")):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
