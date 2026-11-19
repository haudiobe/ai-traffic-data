"""Public-repository confidentiality check for staged changes.

    python -m traffic_annotation.publication build --workbook A.xlsx [--workbook B.xlsx] \
        [--extra TERM ...] --out /outside/repo/denylist.txt
    python -m traffic_annotation.publication check --denylist /outside/repo/denylist.txt [--repo PATH]

``build`` derives a denylist from source workbooks: contributor names from the
Dataset Catalogue, document numbers found anywhere, and all integers with
five or more digits (distinctive measurement values). The denylist itself is
source-derived and must stay outside the repository.

``check`` inspects only what is staged (``git diff --cached``): forbidden file
types, document numbers, denylisted terms and numbers in added lines.
Exit code 1 if anything is found.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config, safety, workbook as wbm

TDOC_RE = re.compile(r"\bS4[a-zA-Z]*-\d{6}\b")
BIGNUM_RE = re.compile(r"(?<![\w.])\d{5,}(?![\w])")


@dataclass
class Hit:
    file: str
    line: int
    kind: str
    term: str


def build_denylist(workbooks, extra=()) -> list:
    terms, numbers = set(), set()
    for path in workbooks:
        wb = wbm.load(Path(path))
        if config.CATALOGUE_SHEET in wb.sheetnames:
            _, recs = wbm.read_table(wb[config.CATALOGUE_SHEET])
            for r in recs:
                c = r.get("Contributor")
                if not config.is_missing(c):
                    terms.add(str(c).strip())
                    terms.update(p.strip() for p in re.split(r"[/;,]", str(c)) if len(p.strip()) > 2)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                for v in row:
                    if isinstance(v, bool) or v is None:
                        continue
                    if isinstance(v, int) and abs(v) >= 10000:
                        numbers.add(str(abs(v)))
                    elif isinstance(v, float) and v.is_integer() and abs(v) >= 10000:
                        numbers.add(str(int(abs(v))))
                    elif isinstance(v, str):
                        terms.update(TDOC_RE.findall(v))
                        numbers.update(n for n in BIGNUM_RE.findall(v.replace(" ", "")) if len(n) >= 5)
    terms.update(t for t in extra if t.strip())
    return sorted(terms, key=str.lower) + sorted(f"#{n}" for n in numbers)


def load_denylist(path: Path):
    terms, numbers = [], set()
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("#") and line[1:].isdigit():
            numbers.add(line[1:])
        else:
            terms.append(line)
    return terms, numbers


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True,
                          encoding="utf-8").stdout


def staged_additions(repo: Path) -> dict:
    """file -> [(line_no, text)] for added lines in the index."""
    out = _git(repo, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff")
    files, cur, ln = {}, None, 0
    for line in out.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
            if cur:
                files.setdefault(cur, [])
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            ln = int(m.group(1)) if m else 0
        elif line.startswith("+") and cur is not None:
            files[cur].append((ln, line[1:]))
            ln += 1
    return files


def check(repo: Path, terms=(), numbers=frozenset()) -> list:
    hits = []
    names = [n for n in _git(repo, "diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines() if n]
    for n in names:
        if Path(n).suffix.lower() in safety.FORBIDDEN_SUFFIXES:
            hits.append(Hit(n, 0, "forbidden-file-type", Path(n).suffix))
    pats = [(t, re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.IGNORECASE)) for t in terms]
    for f, lines in staged_additions(repo).items():
        for ln, text in lines:
            for m in TDOC_RE.findall(text):
                hits.append(Hit(f, ln, "document-number", m))
            for t, p in pats:
                if p.search(text):
                    hits.append(Hit(f, ln, "denylisted-term", t))
            for n in BIGNUM_RE.findall(text):
                if n in numbers:
                    hits.append(Hit(f, ln, "source-number", n))
    return hits


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="traffic-annotation-publication", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--workbook", action="append", required=True, type=Path)
    b.add_argument("--extra", action="append", default=[])
    b.add_argument("--out", required=True, type=Path)
    c = sub.add_parser("check")
    c.add_argument("--denylist", type=Path)
    c.add_argument("--repo", type=Path, default=safety.REPO_ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        safety.assert_outside_repo(a.out)
        items = build_denylist(a.workbook, a.extra)
        a.out.write_text("// source-derived denylist - keep outside the repository\n" + "\n".join(items) + "\n",
                         encoding="utf-8")
        print(f"wrote {len(items)} entries to {a.out}")
        return 0
    terms, numbers = load_denylist(a.denylist) if a.denylist else ([], set())
    hits = check(a.repo, terms, numbers)
    for h in hits:
        # report the kind and location, not the matched source term itself
        print(f"{h.file}:{h.line}: {h.kind}")
    staged = [n for n in _git(a.repo, "diff", "--cached", "--name-only").splitlines() if n]
    print(f"checked {len(staged)} staged file(s) against {len(terms)} terms / {len(numbers)} numbers: "
          f"{'CLEAN' if not hits else str(len(hits)) + ' finding(s)'}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
