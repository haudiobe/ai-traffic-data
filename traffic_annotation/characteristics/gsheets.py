"""Google Sheets synchronization support (dry-run only).

``build_plan`` turns the review tables into an ordered list of operations
(create spreadsheet, ensure tabs, clear, write ranges). ``SheetsSync`` executes
a plan against an injected client. External writes are disabled: with the
default ``dry_run=True`` the plan is only returned/written locally, and a
non-dry run refuses unless ``allow_external_write=True`` *and* a client is
supplied. No Google client library is imported and no network call is made
by this module.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from openpyxl.utils import get_column_letter


class ExternalWriteDisabled(RuntimeError):
    pass


class SheetsClient(Protocol):  # pragma: no cover - interface only
    def create_spreadsheet(self, title: str) -> str: ...
    def ensure_tab(self, spreadsheet_id: str, tab: str) -> None: ...
    def clear(self, spreadsheet_id: str, a1_range: str) -> None: ...
    def update(self, spreadsheet_id: str, a1_range: str, values: list) -> None: ...


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(_cell(x)) for x in v)
    if isinstance(v, float):
        return round(v, 6)
    return v


def build_plan(tables: dict, title: str, spreadsheet_id: str | None = None) -> dict:
    ops = []
    if spreadsheet_id is None:
        ops.append({"op": "create_spreadsheet", "title": title})
    for tab, (headers, rows) in tables.items():
        values = [list(headers)] + [[_cell(v) for v in r] for r in rows]
        last = f"{get_column_letter(len(headers))}{len(values)}"
        ops.append({"op": "ensure_tab", "tab": tab})
        ops.append({"op": "clear", "range": f"'{tab}'!A:ZZ"})
        ops.append({"op": "update", "range": f"'{tab}'!A1:{last}", "rows": len(values),
                    "cols": len(headers), "values": values})
    return {"schema": "traffic-annotation/sheets-sync-plan@1", "title": title,
            "spreadsheet_id": spreadsheet_id, "operations": ops}


def summarize(plan: dict) -> list:
    out = []
    for op in plan["operations"]:
        if op["op"] == "update":
            out.append(f"update {op['range']} ({op['rows']} rows x {op['cols']} cols)")
        elif op["op"] == "create_spreadsheet":
            out.append(f"create spreadsheet '{op['title']}'")
        else:
            out.append(f"{op['op']} {op.get('tab') or op.get('range')}")
    return out


class SheetsSync:
    def __init__(self, client: SheetsClient | None = None, dry_run: bool = True,
                 allow_external_write: bool = False):
        self.client, self.dry_run, self.allow = client, dry_run, allow_external_write

    def run(self, plan: dict) -> list:
        if self.dry_run:
            return summarize(plan)
        if not self.allow or self.client is None:
            raise ExternalWriteDisabled("external writes are disabled; use dry_run=True "
                                        "(set allow_external_write=True and inject a client to enable)")
        sid = plan.get("spreadsheet_id")
        done = []
        for op in plan["operations"]:
            if op["op"] == "create_spreadsheet":
                sid = self.client.create_spreadsheet(op["title"])
            elif op["op"] == "ensure_tab":
                self.client.ensure_tab(sid, op["tab"])
            elif op["op"] == "clear":
                self.client.clear(sid, op["range"])
            elif op["op"] == "update":
                self.client.update(sid, op["range"], op["values"])
            done.append(op["op"])
        return done


def write_plan(plan: dict, path: Path) -> Path:
    Path(path).write_text(json.dumps(plan, indent=1, sort_keys=True, ensure_ascii=False, default=str) + "\n",
                          encoding="utf-8")
    return Path(path)
