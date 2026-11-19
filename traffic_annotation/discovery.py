"""Stage 3 candidate discovery. Output is NOT validated evidence or a CROSSCHECK decision."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from . import safety

PATTERNS = {
 "CH-001": (r"\b(?:uplink|downlink|total|ul|dl)\s+(?:bytes?|volume|traffic|payload|size)\b", r"\b(?:request|response|transfer|payload)\s+(?:bytes?|size)\b"),
 "CH-002": (r"\b(?:uplink|ul)\s+(?:byte\s*rate|bitrate|throughput|rate)\b", r"\bul\s+per\s+(?:turn|request|session)\b"),
 "CH-003": (r"\b(?:downlink|dl)\s+(?:byte\s*rate|bitrate|throughput|rate)\b", r"\bstreaming byte rate\b", r"\bdl\s+per\s+(?:turn|request|session)\b"),
 "CH-004": (r"\b(?:inter[- ]arrival|inter[- ]packet|packet interval|burst on gap|burst off gap|jitter)\b",),
 "CH-005": (r"\b(?:latency|response time|time to first|ttft|turnaround)\b",),
 "CH-006": (r"\b(?:tokens?|chunks?)\s+(?:per|count|rate|size|generated|received)\b", r"\b(?:uplink|downlink|output|input)\s+tokens?\b", r"\bchunk count\b"),
 "CH-007": (r"\b(?:loss tolerance|accuracy|quality degradation|packet loss)\b",),
 "CH-008": (r"\b(?:frame|chunk|audio)\s+(?:cadence|interval|duration|rate)\b", r"\b(?:fps|frames per second|frame rate)\b"),
 "CH-009": (r"\b(?:protocol|tool|agent|mcp|a2a)\s+(?:overhead|bytes?|traffic|messages?)\b",),
 "CH-010": (r"\b(?:number of turns|turn count|turns per|session turns|total turns|interaction count)\b", r"^turns$")
}
REGEX = {k:tuple(re.compile(p,re.I) for p in v) for k,v in PATTERNS.items()}
EXCLUDE = {"0. Index","Dataset Catalogue","Characteristic Evidence","Provenance History","Status Definitions","Dataset Status Register"}

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    return h.hexdigest()

def _numbers(row,ri):
    return [{"cell":f"{get_column_letter(ci)}{ri}","value":v}
            for ci,v in enumerate(row,1) if isinstance(v,(int,float)) and not isinstance(v,bool)]

def discover(source):
    source=Path(source)
    before=sha256(source)
    w=load_workbook(source,read_only=True,data_only=False)
    sheet_to_ids=defaultdict(list)
    if "Dataset Catalogue" in w.sheetnames:
        rows=w["Dataset Catalogue"].iter_rows(values_only=True)
        hdr=next(rows)
        col={str(v).strip():i for i,v in enumerate(hdr) if v is not None}
        a,b=col.get("Dataset ID"),col.get("Parent sheet")
        if a is not None and b is not None:
            for row in rows:
                if len(row)>max(a,b) and row[a] and row[b] and str(row[b]).strip() in w.sheetnames:
                    sheet_to_ids[str(row[b]).strip()].append(str(row[a]).strip())
    found=[]
    sheets=[]
    for sh in w:
        if sh.title in EXCLUDE:continue
        # Preserve only source-scoped candidate rows; never assert that matches
        # are metric-level equivalent or attributable to independent organizations.
        rows=list(sh.iter_rows(values_only=True))
        counts=defaultdict(int)
        for ri,row in enumerate(rows,1):
            for ci,value in enumerate(row[:12],1):
                if not isinstance(value,str) or not value.strip():continue
                labels=[cid for cid,patterns in REGEX.items() if any(p.search(value.strip()) for p in patterns)]
                if not labels:continue
                if ci<=2:
                    numbers=_numbers(row,ri)
                else:
                    numbers=[]
                    for j in range(ri,min(ri+12,len(rows))):
                        v=rows[j][ci-1] if ci-1<len(rows[j]) else None
                        if isinstance(v,(int,float)) and not isinstance(v,bool):
                            numbers.append({"cell":f"{get_column_letter(ci)}{j+1}","value":v})
                if not numbers:continue
                for cid in labels:
                    counts[cid]+=1
                    found.append({"characteristic_id":cid,"sheet":sh.title,
                        "label_cell":f"{get_column_letter(ci)}{ri}","label":value.strip(),
                        "dataset_ids":sorted(sheet_to_ids.get(sh.title,[])),
                        "numeric_cells":numbers,"review_status":"CANDIDATE_UNVERIFIED"})
        sheets.append({"sheet":sh.title,"candidate_counts":dict(sorted(counts.items()))})
    w.close()
    if before!=sha256(source):raise RuntimeError("Source workbook changed during discovery")
    found.sort(key=lambda x:(x["characteristic_id"],x["sheet"],int(re.search(r"\d+",x["label_cell"]).group()),x["label_cell"]))
    chars={cid:{"candidate_rows":sum(x["characteristic_id"]==cid for x in found),
                "candidate_sheets":sorted({x["sheet"] for x in found if x["characteristic_id"]==cid}),
                "verified_evidence":0,"crosscheck_change":"NONE"} for cid in PATTERNS}
    return {"schema":"traffic-annotation/discovery@1","source_sha256":before,
            "warning":"Keyword candidates are not verified evidence; no crosscheck outcome is inferred.",
            "characteristics":chars,"sheets":sheets,"candidates":found}

def write_outputs(result,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/"candidate_measurements.json").write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    with (out/"candidate_measurements.csv").open("w",encoding="utf-8",newline="") as f:
        wr=csv.writer(f)
        wr.writerow(["characteristic","sheet","label_cell","label","dataset_ids","numeric_cells","review_status"])
        for c in result["candidates"]:
            wr.writerow([c["characteristic_id"],c["sheet"],c["label_cell"],c["label"],";".join(c["dataset_ids"]),
                         ";".join(f"{x['cell']}={x['value']}" for x in c["numeric_cells"]),c["review_status"]])
    with (out/"discovery_summary.csv").open("w",encoding="utf-8",newline="") as f:
        wr=csv.writer(f);wr.writerow(["characteristic","candidate_rows","candidate_sheets","verified_evidence","status"])
        for cid,d in sorted(result["characteristics"].items()):
            wr.writerow([cid,d["candidate_rows"],len(d["candidate_sheets"]),0,"NOT_ASSESSED_BY_DISCOVERY"])

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workbook",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    args=p.parse_args(argv)
    safety.assert_outside_repo(args.workbook,args.out)
    result=discover(args.workbook)
    write_outputs(result,args.out)
    for cid,d in result["characteristics"].items():
        print(f"{cid}: {d['candidate_rows']} candidate locations; 0 verified by discovery")
    print("Source integrity verified; workbook statuses and CROSSCHECK states unchanged.")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
